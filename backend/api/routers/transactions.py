import csv
import io
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from redis.exceptions import RedisError
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from api.database import get_session
from api.models import Account, Transaction
from shared.constants import TRANSACTION_EVENT_CHANNEL, TransactionStatus
from shared.schemas import (
    FraudRatePoint,
    TransactionMetrics,
    TransactionPage,
    TransactionRead,
    TransactionVolumePoint,
)

router = APIRouter(prefix="/transactions", tags=["transactions"])
SessionDependency = Annotated[AsyncSession, Depends(get_session)]


def _transaction_filters(search: str | None) -> list[ColumnElement[bool]]:
    filters: list[ColumnElement[bool]] = []
    if search and search.strip():
        term = f"%{search.strip()}%"
        filters.append(
            or_(
                Transaction.tx_hash.ilike(term),
                Account.external_ref.ilike(term),
                Account.name.ilike(term),
                Transaction.location_country.ilike(term),
                Transaction.jurisdiction.ilike(term),
            )
        )
    return filters


async def _matched_transactions(
    db: AsyncSession,
    *,
    search: str | None,
    status_filter: TransactionStatus | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[Transaction]:
    stmt = select(Transaction).join(Account, Transaction.account_id == Account.id)
    conditions = _transaction_filters(search)
    if status_filter is not None:
        conditions.append(Transaction.status == status_filter)
    if conditions:
        stmt = stmt.where(*conditions)
    stmt = stmt.order_by(Transaction.ingested_at.desc(), Transaction.id)
    if limit is not None:
        stmt = stmt.limit(limit)
    if offset:
        stmt = stmt.offset(offset)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("", response_model=TransactionPage)
async def list_transactions(
    db: SessionDependency,
    search: str | None = None,
    status_filter: Annotated[TransactionStatus | None, Query(alias="status")] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> TransactionPage:
    conditions = _transaction_filters(search)
    counts_stmt = (
        select(Transaction.status, func.count(Transaction.id))
        .join(Account, Transaction.account_id == Account.id)
        .group_by(Transaction.status)
    )
    if conditions:
        counts_stmt = counts_stmt.where(*conditions)
    count_result = await db.execute(counts_stmt)
    status_counts = {value: 0 for value in TransactionStatus}
    for tx_status, count in count_result.all():
        status_counts[TransactionStatus(tx_status)] = count

    transactions = await _matched_transactions(
        db,
        search=search,
        status_filter=status_filter,
        limit=limit,
        offset=offset,
    )
    total = sum(status_counts.values()) if status_filter is None else status_counts[status_filter]
    return TransactionPage(
        items=[TransactionRead.model_validate(tx) for tx in transactions],
        status_counts=status_counts,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/stream",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {"schema": {"type": "string"}}}}},
)
async def transaction_stream(request: Request) -> StreamingResponse:
    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        raise HTTPException(status_code=503, detail="Redis event stream is unavailable")

    async def event_stream() -> AsyncIterator[str]:
        pubsub = redis.pubsub()
        try:
            await pubsub.subscribe(TRANSACTION_EVENT_CHANNEL)
            while not await request.is_disconnected():
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=15,
                )
                if message is None:
                    yield ": heartbeat\n\n"
                    continue
                payload = message.get("data")
                if isinstance(payload, bytes):
                    payload = payload.decode("utf-8")
                yield f"event: transaction\ndata: {payload}\n\n"
        except RedisError as exc:
            raise RuntimeError("Redis transaction event stream failed") from exc
        finally:
            await pubsub.unsubscribe(TRANSACTION_EVENT_CHANNEL)
            await pubsub.aclose()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/export.csv")
async def export_transactions(
    db: SessionDependency,
    search: str | None = None,
    status_filter: Annotated[TransactionStatus | None, Query(alias="status")] = None,
) -> StreamingResponse:
    transactions = await _matched_transactions(
        db,
        search=search,
        status_filter=status_filter,
    )

    async def csv_rows() -> AsyncIterator[str]:
        output = io.StringIO()
        writer = csv.writer(output)
        headers = (
            "id",
            "tx_hash",
            "account_id",
            "amount",
            "currency",
            "country",
            "occurred_at",
            "status",
        )
        writer.writerow(headers)
        yield output.getvalue()
        for tx in transactions:
            output.seek(0)
            output.truncate(0)
            writer.writerow(
                (
                    tx.id,
                    tx.tx_hash,
                    tx.account_id,
                    tx.amount,
                    tx.currency,
                    tx.location_country or tx.jurisdiction,
                    tx.occurred_at.isoformat(),
                    tx.status,
                )
            )
            yield output.getvalue()

    return StreamingResponse(
        csv_rows(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="transactions.csv"'},
    )


metrics_router = APIRouter(tags=["transactions"])


@metrics_router.get("/metrics/transactions", response_model=TransactionMetrics)
async def transaction_metrics(
    db: SessionDependency,
    time_range: Annotated[Literal["24h", "1h", "live"], Query(alias="range")] = "24h",
    fraud_rate_threshold: float = Query(0.05, ge=0, le=1),
) -> TransactionMetrics:
    """Aggregate recent activity by ingestion time for live monitoring charts."""
    now = datetime.now(UTC)
    duration_seconds, bucket_seconds = {
        "24h": (24 * 60 * 60, 60 * 60),
        "1h": (60 * 60, 5 * 60),
        "live": (60, 5),
    }[time_range]
    start = now - timedelta(seconds=duration_seconds)
    result = await db.execute(
        select(Transaction).where(
            Transaction.ingested_at >= start,
            Transaction.ingested_at <= now,
        )
    )
    transactions = list(result.scalars().all())
    bucket_count = duration_seconds // bucket_seconds
    bucket_volumes = [Decimal("0") for _ in range(bucket_count)]
    bucket_counts = [0 for _ in range(bucket_count)]
    bucket_flagged = [0 for _ in range(bucket_count)]

    for tx in transactions:
        index = min(
            bucket_count - 1,
            max(0, int((tx.ingested_at - start).total_seconds() // bucket_seconds)),
        )
        bucket_volumes[index] += tx.amount
        bucket_counts[index] += 1
        if tx.status == TransactionStatus.FLAGGED:
            bucket_flagged[index] += 1

    volume_series = [
        TransactionVolumePoint(
            timestamp=start + timedelta(seconds=index * bucket_seconds),
            volume=bucket_volumes[index],
            transaction_count=bucket_counts[index],
        )
        for index in range(bucket_count)
    ]
    fraud_rate_series = [
        FraudRatePoint(
            timestamp=start + timedelta(seconds=index * bucket_seconds),
            fraud_rate=(
                bucket_flagged[index] / bucket_counts[index] if bucket_counts[index] else 0.0
            ),
        )
        for index in range(bucket_count)
    ]
    return TransactionMetrics(
        range=time_range,
        throughput_tx_s=len(transactions) / duration_seconds,
        total_count=len(transactions),
        volume_series=volume_series,
        fraud_rate_series=fraud_rate_series,
        fraud_rate_threshold=fraud_rate_threshold,
    )
