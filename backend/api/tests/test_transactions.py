import asyncio
import csv
import io
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from api.models import Transaction
from api.routers.transactions import (
    export_transactions,
    list_transactions,
    transaction_metrics,
    transaction_stream,
)
from shared.constants import TransactionStatus


class FakeScalars:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def all(self) -> list[object]:
        return self._rows


class FakeResult:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def scalars(self) -> FakeScalars:
        return FakeScalars(self._rows)

    def all(self) -> list[object]:
        return self._rows


class FakeSession:
    def __init__(self, *results: FakeResult) -> None:
        self.results = list(results)
        self.statements: list[object] = []

    async def execute(self, statement: object) -> FakeResult:
        self.statements.append(statement)
        return self.results.pop(0)


class FakePubSub:
    def __init__(self, messages: list[dict[str, object] | None]) -> None:
        self.messages = iter(messages)
        self.subscribed: list[str] = []
        self.unsubscribed: list[str] = []
        self.timeouts: list[object] = []
        self.closed = False

    async def subscribe(self, channel: str) -> None:
        self.subscribed.append(channel)

    async def get_message(self, **kwargs: object) -> dict[str, object] | None:
        self.timeouts.append(kwargs.get("timeout"))
        return next(self.messages)

    async def unsubscribe(self, channel: str) -> None:
        self.unsubscribed.append(channel)

    async def aclose(self) -> None:
        self.closed = True


def make_transaction(
    *,
    status: str = "cleared",
    tx_hash: str = "hash-1",
    country: str = "US",
    occurred_at: datetime | None = None,
    amount: Decimal = Decimal("100.00"),
) -> Transaction:
    now = datetime.now(UTC)
    return Transaction(
        id=uuid4(),
        idempotency_key=f"idem-{uuid4()}",
        tx_hash=tx_hash,
        account_id=uuid4(),
        amount=amount,
        currency="USD",
        jurisdiction=country,
        location_country=country,
        direction="outflow",
        tx_type="TRANSFER",
        occurred_at=occurred_at or now,
        ingested_at=now,
        risk_score=70,
        status=status,
    )


def test_list_transactions_returns_items_counts_and_limit() -> None:
    rows = [make_transaction(status=state) for state in ("cleared", "review")]
    session = FakeSession(
        FakeResult([(TransactionStatus.CLEARED, 1), (TransactionStatus.REVIEW, 2)]),
        FakeResult([rows[1]]),
    )

    response = asyncio.run(
        list_transactions(
            db=session,  # type: ignore[arg-type]
            search="US",
            status_filter=TransactionStatus.REVIEW,
            limit=10,
            offset=5,
        )
    )

    assert len(response.items) == 1
    assert response.items[0].status == TransactionStatus.REVIEW
    assert response.status_counts == {
        TransactionStatus.CLEARED: 1,
        TransactionStatus.REVIEW: 2,
        TransactionStatus.FLAGGED: 0,
    }
    assert response.total == 2
    assert response.limit == 10
    assert response.offset == 5
    assert "transactions.ingested_at DESC" in str(session.statements[1]._order_by_clauses[0])


def test_transaction_metrics_builds_bucketed_series_and_threshold() -> None:
    now = datetime.now(UTC)
    transactions = [
        make_transaction(status="flagged", occurred_at=now - timedelta(seconds=15)),
        make_transaction(status="cleared", occurred_at=now - timedelta(seconds=10)),
    ]
    session = FakeSession(FakeResult(transactions))

    metrics = asyncio.run(
        transaction_metrics(
            db=session,  # type: ignore[arg-type]
            time_range="live",
            fraud_rate_threshold=0.12,
        )
    )

    assert metrics.range == "live"
    assert metrics.total_count == 2
    assert metrics.throughput_tx_s > 0
    assert len(metrics.volume_series) == 12
    assert len(metrics.fraud_rate_series) == 12
    assert sum(point.transaction_count for point in metrics.volume_series) == 2
    assert sum(point.fraud_rate > 0 for point in metrics.fraud_rate_series) == 1
    assert metrics.fraud_rate_threshold == 0.12
    assert "transactions.ingested_at" in str(session.statements[0].whereclause)


def test_transaction_export_csv_applies_status_filter() -> None:
    transaction = make_transaction(status="flagged", tx_hash="export-hash", country="GB")
    session = FakeSession(FakeResult([transaction]))

    response = asyncio.run(
        export_transactions(
            db=session,  # type: ignore[arg-type]
            search="GB",
            status_filter=TransactionStatus.FLAGGED,
        )
    )

    async def read_body() -> str:
        chunks = [chunk async for chunk in response.body_iterator]
        if chunks and isinstance(chunks[0], bytes):
            return b"".join(chunks).decode()
        return "".join(chunks)

    text = asyncio.run(read_body())
    rows = list(csv.DictReader(io.StringIO(text)))
    assert response.media_type == "text/csv"
    assert len(rows) == 1
    assert rows[0]["tx_hash"] == "export-hash"
    assert rows[0]["country"] == "GB"
    assert rows[0]["status"] == "flagged"


def test_transaction_stream_publishes_events_and_heartbeats() -> None:
    pubsub = FakePubSub(
        [
            {"type": "message", "data": '{"tx_hash":"stream-hash"}'},
            None,
        ]
    )
    redis = SimpleNamespace(pubsub=lambda: pubsub)
    disconnect_checks = iter((False, False, True))

    async def is_disconnected() -> bool:
        return next(disconnect_checks)

    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(redis=redis)),
        is_disconnected=is_disconnected,
    )
    response = asyncio.run(transaction_stream(request))  # type: ignore[arg-type]

    async def read_body() -> list[str]:
        chunks = [chunk async for chunk in response.body_iterator]
        return [
            chunk.decode() if isinstance(chunk, bytes) else chunk
            for chunk in chunks
        ]

    body = asyncio.run(read_body())
    assert any("event: transaction" in chunk and "stream-hash" in chunk for chunk in body)
    assert any(": heartbeat" in chunk for chunk in body)
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache, no-transform"
    assert response.headers["connection"] == "keep-alive"
    assert response.headers["x-accel-buffering"] == "no"
    assert pubsub.subscribed == ["tx:events"]
    assert pubsub.unsubscribed == ["tx:events"]
    assert pubsub.timeouts == [15, 15]
    assert pubsub.closed
