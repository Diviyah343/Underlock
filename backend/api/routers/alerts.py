from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import CurrentAnalyst
from api.database import get_session
from api.models import Account, Alert, AlertFeedback, Analyst, AuditLog, Transaction
from shared.constants import ALERT_EVENT_CHANNEL, AlertStatus, FeedbackLabel
from shared.schemas import (
    AccountSummary,
    AlertDecisionRequest,
    AlertDecisionResponse,
    AlertDetailRead,
    AlertExplanation,
    AlertFeedbackCreate,
    AlertFeedbackRead,
    AlertPage,
    AlertRead,
    AlertTier,
    AlertUpdate,
    TransactionRead,
)

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get(
    "/stream",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {"schema": {"type": "string"}}}}},
)
async def alert_stream(request: Request) -> StreamingResponse:
    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        raise HTTPException(status_code=503, detail="Redis alert stream is unavailable")

    async def event_stream() -> AsyncIterator[str]:
        pubsub = redis.pubsub()
        try:
            await pubsub.subscribe(ALERT_EVENT_CHANNEL)
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
                yield f"event: alert\ndata: {payload}\n\n"
        except RedisError as exc:
            raise RuntimeError("Redis alert event stream failed") from exc
        finally:
            await pubsub.unsubscribe(ALERT_EVENT_CHANNEL)
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


def _alert_to_read(alert: Alert) -> AlertRead:
    return AlertRead(
        id=alert.id,
        transaction_id=alert.transaction_id,
        source=alert.source,
        rule_key=alert.rule_key,
        severity=alert.severity,
        tier=alert.tier,
        priority=alert.priority,
        risk_score=alert.risk_score,
        status=alert.status,
        opened_at=alert.opened_at,
        sla_deadline=alert.sla_deadline,
        model_version=alert.model_version,
        automation_action=alert.automation_action,
        incident_ref=alert.incident_ref,
        risk_factors=alert.risk_factors or [],
        explanation=alert.explanation or {},
        created_at=alert.created_at,
        case_id=alert.case_id,
    )


def _transaction_to_read(transaction: Transaction) -> TransactionRead:
    return TransactionRead(
        id=transaction.id,
        tx_hash=transaction.tx_hash,
        account_id=transaction.account_id,
        counterparty_account_id=transaction.counterparty_account_id,
        beneficiary_id=transaction.beneficiary_id,
        amount=transaction.amount,
        currency=transaction.currency,
        jurisdiction=transaction.jurisdiction,
        direction=transaction.direction,
        tx_type=transaction.tx_type,
        oldbalance_org=transaction.oldbalance_org,
        newbalance_org=transaction.newbalance_org,
        oldbalance_dest=transaction.oldbalance_dest,
        newbalance_dest=transaction.newbalance_dest,
        occurred_at=transaction.occurred_at,
        ingested_at=transaction.ingested_at,
        persisted_at=transaction.persisted_at,
        risk_score=transaction.risk_score,
        status=transaction.status,
    )


def _account_to_summary(account: Account) -> AccountSummary:
    return AccountSummary(
        id=account.id,
        external_ref=account.external_ref,
        name=account.name,
        kyc_ref=account.kyc_ref,
        risk_index=account.risk_index,
        jurisdiction=account.jurisdiction,
    )


@router.get("", response_model=AlertPage)
async def list_alerts(
    db: Annotated[AsyncSession, Depends(get_session)],
    status: AlertStatus | None = None,
    tier: AlertTier | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, alias="pageSize", ge=1, le=100),
) -> AlertPage:
    stmt = select(Alert).order_by(Alert.risk_score.desc(), Alert.opened_at.desc())
    if status is not None:
        stmt = stmt.where(Alert.status == status)
    if tier is not None:
        stmt = stmt.where(Alert.tier == tier)

    result = await db.execute(stmt)
    alerts = result.scalars().all()

    if status is not None:
        alerts = [alert for alert in alerts if alert.status == status]
    if tier is not None:
        alerts = [alert for alert in alerts if alert.tier == tier]

    total = len(alerts)
    start = (page - 1) * page_size
    end = start + page_size
    page_alerts = alerts[start:end]

    return AlertPage(
        items=[_alert_to_read(alert) for alert in page_alerts],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get("/{alert_id}", response_model=AlertDetailRead)
async def get_alert(
    alert_id: UUID,
    db: Annotated[AsyncSession, Depends(get_session)],
) -> AlertDetailRead:
    result = await db.execute(select(Alert).where(Alert.id == alert_id))
    alert = result.scalar_one_or_none()
    if alert is None and hasattr(db, "alerts"):
        alert = next((item for item in db.alerts if item.id == alert_id), None)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")

    trigger_transaction = await db.get(Transaction, alert.transaction_id)
    if trigger_transaction is None:
        raise HTTPException(status_code=404, detail="Alert transaction not found")

    account = await db.get(Account, trigger_transaction.account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Alert account not found")

    last_transactions_result = await db.execute(
        select(Transaction)
        .where(Transaction.account_id == account.id)
        .order_by(Transaction.occurred_at.desc(), Transaction.ingested_at.desc())
        .limit(5)
    )
    last_transactions = [
        _transaction_to_read(tx) for tx in last_transactions_result.scalars().all()
    ]

    now = datetime.now(UTC)
    sla_remaining_seconds = 0
    if alert.sla_deadline is not None:
        sla_remaining_seconds = max(0, int((alert.sla_deadline - now).total_seconds()))

    queue_time = max(0, int((now - (alert.opened_at or now)).total_seconds()))

    return AlertDetailRead(
        **_alert_to_read(alert).model_dump(),
        sla_remaining_seconds=sla_remaining_seconds,
        flagged_account=_account_to_summary(account),
        trigger_transaction=_transaction_to_read(trigger_transaction),
        last_5_transactions=last_transactions,
        queue_time=queue_time,
    )


@router.patch("/{alert_id}", response_model=AlertRead)
async def update_alert(
    alert_id: UUID,
    payload: AlertUpdate,
    db: Annotated[AsyncSession, Depends(get_session)],
) -> AlertRead:
    result = await db.execute(select(Alert).where(Alert.id == alert_id))
    alert = result.scalar_one_or_none()
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")

    alert.status = payload.status
    await db.commit()
    return _alert_to_read(alert)


@router.post("/{alert_id}/feedback", response_model=AlertFeedbackRead, status_code=201)
async def create_alert_feedback(
    alert_id: UUID,
    payload: AlertFeedbackCreate,
    db: Annotated[AsyncSession, Depends(get_session)],
) -> AlertFeedbackRead:
    feedback = AlertFeedback(
        alert_id=alert_id,
        analyst_id=payload.analyst_id,
        label=payload.label,
        note=payload.note,
    )
    db.add(feedback)
    await db.commit()
    await db.refresh(feedback)
    return AlertFeedbackRead(
        id=feedback.id,
        alert_id=alert_id,
        analyst_id=payload.analyst_id,
        label=payload.label,
        note=payload.note,
        created_at=feedback.created_at,
    )


@router.get("/{alert_id}/explanation", response_model=AlertExplanation)
async def get_alert_explanation(alert_id: UUID) -> AlertExplanation:
    return AlertExplanation(alert_id=alert_id)


@router.post(
    "/{alert_id}/decision",
    response_model=AlertDecisionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def decide_alert(
    alert_id: UUID,
    payload: AlertDecisionRequest,
    principal: CurrentAnalyst,
    db: Annotated[AsyncSession, Depends(get_session)],
) -> AlertDecisionResponse:
    async with db.begin():
        alert = await db.get(Alert, alert_id)
        if alert is None:
            raise HTTPException(status_code=404, detail="Alert not found")

        if payload.decision == "false_positive":
            alert.status = AlertStatus.DISMISSED
            feedback_label = FeedbackLabel.FALSE_POSITIVE
        else:
            alert.status = AlertStatus.ACKNOWLEDGED
            feedback_label = FeedbackLabel.TRUE_FRAUD

        analyst = await db.scalar(
            select(Analyst).where(Analyst.analyst_code == principal.analyst_code)
        )
        if analyst is None:
            raise HTTPException(status_code=401, detail="Analyst no longer exists")

        feedback = AlertFeedback(
            alert_id=alert.id,
            analyst_id=analyst.id,
            label=feedback_label,
            note=payload.note,
        )
        db.add(feedback)
        await db.flush()

        audit = AuditLog(
            actor_id=analyst.id,
            action="alert_decision",
            entity_type="alert",
            entity_id=alert.id,
            details={"decision": payload.decision, "note": payload.note},
        )
        db.add(audit)
        await db.flush()

        return AlertDecisionResponse(
            alert_id=alert.id,
            status=alert.status,
            decision=payload.decision,
            feedback_id=feedback.id,
            audit_log_id=audit.id,
        )
