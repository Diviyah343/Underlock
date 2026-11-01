import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from api.auth import AnalystPrincipal
from api.models import Account, Alert, AlertFeedback, Analyst, AuditLog, Transaction
from api.routers.alerts import alert_stream, decide_alert, get_alert, list_alerts
from shared.constants import AlertStatus, FeedbackLabel
from shared.schemas import AlertDecisionRequest


class FakeResult:
    def __init__(self, rows: list[object] | None = None) -> None:
        self._rows = rows or []

    def scalars(self) -> "FakeScalars":
        return FakeScalars(self._rows)

    def scalar_one_or_none(self) -> object | None:
        return self._rows[0] if self._rows else None


class FakeScalars:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def all(self) -> list[object]:
        return self._rows


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


class FakeSession:
    def __init__(
        self,
        alerts: list[Alert] | None = None,
        accounts: list[Account] | None = None,
        transactions: list[Transaction] | None = None,
    ) -> None:
        self.alerts = alerts or []
        self.accounts = accounts or []
        self.transactions = transactions or []
        self.analysts = [
            Analyst(
                id=uuid4(),
                name="Eleni Vance",
                analyst_code="AN-8902",
                role="Senior Analyst",
                email="eleni.vance@example.com",
            )
        ]
        self.alert_map = {alert.id: alert for alert in self.alerts}
        self.account_map = {account.id: account for account in self.accounts}
        self.transaction_map = {transaction.id: transaction for transaction in self.transactions}
        self.feedback: list[AlertFeedback] = []
        self.audit_logs: list[AuditLog] = []
        self._analysts: list[object] = []

    async def execute(self, statement: object) -> FakeResult:
        statement_text = str(statement)
        if "transactions" in statement_text:
            return FakeResult(list(self.transactions))
        return FakeResult(list(self.alerts))

    async def scalar(self, _statement: object) -> object | None:
        return self.analysts[0]

    async def get(self, model: type[object], pk: object) -> object | None:
        if model is Alert:
            return self.alert_map.get(pk)
        if model is Transaction:
            return self.transaction_map.get(pk)
        if model is Account:
            return self.account_map.get(pk)
        return None

    async def commit(self) -> None:
        return None

    async def refresh(self, obj: object) -> None:
        return None

    async def flush(self) -> None:
        return None

    def add(self, obj: object) -> None:
        if isinstance(obj, AlertFeedback):
            self.feedback.append(obj)
            if getattr(obj, "id", None) is None:
                obj.id = uuid4()
        elif isinstance(obj, AuditLog):
            self.audit_logs.append(obj)
            if getattr(obj, "id", None) is None:
                obj.id = uuid4()
        elif hasattr(obj, "analyst_code"):
            self._analysts.append(obj)
            if getattr(obj, "id", None) is None:
                obj.id = uuid4()

    class _BeginContext:
        def __init__(self, session: "FakeSession") -> None:
            self.session = session

        async def __aenter__(self) -> "FakeSession":
            return self.session

        async def __aexit__(self, exc_type: object, exc: object, tb: object) -> bool:
            return False

    def begin(self) -> "FakeSession._BeginContext":
        return self._BeginContext(self)


def make_alert(
    alert_id: object,
    transaction_id: object,
    *,
    tier: str = "high",
    status: str = "open",
    risk_score: int = 70,
    opened_at: datetime | None = None,
) -> Alert:
    now = datetime.now(UTC)
    return Alert(
        id=alert_id,
        transaction_id=transaction_id,
        source="rule",
        severity="high",
        rule_key="new-device-transfer",
        risk_score=risk_score,
        status=status,
        tier=tier,
        priority="P1-AML",
        opened_at=opened_at or (now - timedelta(hours=1)),
        sla_deadline=(now + timedelta(hours=3)),
        model_version="v1.2.3",
        automation_action="HOLD_DISBURSEMENT",
        incident_ref="INC-101",
        risk_factors=[
            {"title": "Device mismatch", "weight_pct": 60, "description": "New device"},
            {"title": "Geo jump", "weight_pct": 40, "description": "High-risk location"},
        ],
        explanation={"summary": "Suspicious transfer"},
        created_at=now - timedelta(minutes=20),
        case_id=None,
    )


def make_account(account_id: object) -> Account:
    return Account(
        id=account_id,
        external_ref="ACCT-1001",
        name="Northwind Holdings",
        kyc_ref="KYC-1001",
        jurisdiction="US",
        risk_index=83,
    )


def make_transaction(transaction_id: object, account_id: object) -> Transaction:
    now = datetime.now(UTC)
    return Transaction(
        id=transaction_id,
        idempotency_key=f"txn-{transaction_id}",
        tx_hash=f"hash-{transaction_id}",
        account_id=account_id,
        amount=1500,
        currency="USD",
        jurisdiction="US",
        ip="203.0.113.12",
        location_country="US",
        device_signature="dev-123",
        origin_channel="web",
        beneficiary_entity="Example Beneficiary",
        beneficiary_bank="HSBC",
        direction="outflow",
        tx_type="TRANSFER",
        occurred_at=now - timedelta(minutes=5),
        ingested_at=now - timedelta(minutes=4),
        persisted_at=now - timedelta(minutes=3),
        risk_score=78,
        status="flagged",
        model_version="v1.2.3",
    )


def test_alert_stream_publishes_events_and_heartbeats() -> None:
    pubsub = FakePubSub(
        [
            {"type": "message", "data": '{"id":"alert-id"}'},
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
    response = asyncio.run(alert_stream(request))

    async def read_body() -> list[str]:
        chunks = [chunk async for chunk in response.body_iterator]
        return [chunk.decode() if isinstance(chunk, bytes) else chunk for chunk in chunks]

    body = asyncio.run(read_body())
    assert any("event: alert" in chunk and "alert-id" in chunk for chunk in body)
    assert any(": heartbeat" in chunk for chunk in body)
    assert response.media_type == "text/event-stream"
    assert response.headers["cache-control"] == "no-cache, no-transform"
    assert response.headers["connection"] == "keep-alive"
    assert response.headers["x-accel-buffering"] == "no"
    assert pubsub.subscribed == ["alert:events"]
    assert pubsub.unsubscribed == ["alert:events"]
    assert pubsub.timeouts == [15, 15]
    assert pubsub.closed


def test_list_alerts_filters_and_paginates() -> None:
    alert_one = make_alert(uuid4(), uuid4(), tier="high", risk_score=92)
    alert_two = make_alert(uuid4(), uuid4(), tier="high", risk_score=81)
    alert_three = make_alert(uuid4(), uuid4(), tier="med", risk_score=40, status="acknowledged")
    session = FakeSession(alerts=[alert_one, alert_two, alert_three])

    response = asyncio.run(
        list_alerts(status=AlertStatus.OPEN, tier="high", page=1, page_size=10, db=session)
    )

    assert response.total == 2
    assert [item.risk_score for item in response.items] == [92, 81]
    assert all(item.status == AlertStatus.OPEN for item in response.items)


def test_get_alert_detail_and_decision_transaction() -> None:
    account_id = uuid4()
    tx_id = uuid4()
    alert_id = uuid4()
    account = make_account(account_id)
    trigger_tx = make_transaction(tx_id, account_id)
    alert = make_alert(alert_id, tx_id, tier="high")
    older_tx = make_transaction(uuid4(), account_id)
    older_tx.occurred_at = datetime.now(UTC) - timedelta(days=2)
    newer_tx = make_transaction(uuid4(), account_id)
    newer_tx.occurred_at = datetime.now(UTC) - timedelta(days=1)
    session = FakeSession(
        alerts=[alert],
        accounts=[account],
        transactions=[trigger_tx, older_tx, newer_tx],
    )

    detail = asyncio.run(get_alert(alert_id, db=session))
    assert detail.flagged_account is not None
    assert detail.flagged_account.external_ref == "ACCT-1001"
    assert detail.trigger_transaction is not None
    assert detail.trigger_transaction.id == tx_id
    assert len(detail.last_5_transactions) >= 1
    assert detail.sla_remaining_seconds >= 0
    assert detail.queue_time >= 0
    assert detail.risk_factors[0].title == "Device mismatch"

    decision = asyncio.run(
        decide_alert(
            alert_id,
            AlertDecisionRequest(decision="false_positive", note="Duplicate alert"),
            principal=AnalystPrincipal("AN-8902", "test-jti", 2_000_000_000),
            db=session,
        )
    )

    assert decision.status == AlertStatus.DISMISSED
    assert decision.decision == "false_positive"
    assert len(session.feedback) == 1
    assert session.feedback[0].label == FeedbackLabel.FALSE_POSITIVE
    assert session.feedback[0].note == "Duplicate alert"
    assert len(session.audit_logs) == 1
    assert session.audit_logs[0].details["decision"] == "false_positive"
