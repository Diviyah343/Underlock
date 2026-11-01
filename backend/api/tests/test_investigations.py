import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from api.models import Account, Alert, Analyst, Case, CaseAlert
from api.routers.investigations import (
    create_investigation,
    investigation_graph,
    investigation_stats,
    list_investigations,
)
from shared.schemas import InvestigationCreate


class FakeResult:
    def __init__(self, rows: list[object] | None = None, one: object | None = None) -> None:
        self.rows = rows or []
        self.one_value = one

    def scalars(self) -> "FakeScalars":
        return FakeScalars(self.rows)

    def all(self) -> list[object]:
        return self.rows

    def one(self) -> object:
        assert self.one_value is not None
        return self.one_value


class FakeScalars:
    def __init__(self, rows: list[object]) -> None:
        self.rows = rows

    def all(self) -> list[object]:
        return self.rows


class FakeSession:
    def __init__(
        self,
        *,
        scalar: object | None = None,
        results: list[FakeResult] | None = None,
        cases: list[Case] | None = None,
        alerts: list[Alert] | None = None,
        analysts: list[Analyst] | None = None,
        accounts: list[Account] | None = None,
    ) -> None:
        self.scalar_value = scalar
        self.results = list(results or [])
        self.cases = {case.id: case for case in cases or []}
        self.alerts = {alert.id: alert for alert in alerts or []}
        self.analysts = {analyst.id: analyst for analyst in analysts or []}
        self.accounts = list(accounts or [])
        self.added: list[object] = []

    async def scalar(self, _statement: object) -> object | None:
        return self.scalar_value

    async def execute(self, _statement: object) -> FakeResult:
        return self.results.pop(0)

    async def get(self, model: type[object], identity: object) -> object | None:
        if model is Case:
            return self.cases.get(identity)
        if model is Analyst:
            return self.analysts.get(identity)
        return None

    def add(self, item: object) -> None:
        self.added.append(item)

    async def flush(self) -> None:
        for item in self.added:
            if isinstance(item, Case) and item.id is None:
                item.id = uuid4()

    class _Transaction:
        async def __aenter__(self) -> None:
            return None

        async def __aexit__(self, *_args: object) -> bool:
            return False

    def begin(self) -> "FakeSession._Transaction":
        return self._Transaction()


def make_case(*, status: str = "open") -> Case:
    now = datetime.now(UTC)
    return Case(
        id=uuid4(),
        case_code="INV-2026-001",
        title="Suspicious wire activity",
        status=status,
        assigned_analyst_id=None,
        opened_at=now - timedelta(days=1),
        last_activity_at=now,
    )


def make_alert(transaction_id: object, alert_id: object | None = None) -> Alert:
    now = datetime.now(UTC)
    return Alert(
        id=alert_id or uuid4(),
        transaction_id=transaction_id,
        source="rule",
        severity="high",
        risk_score=86,
        status="open",
        created_at=now,
        case_id=None,
    )


def make_account(account_id: object, external_ref: str) -> Account:
    return Account(
        id=account_id,
        external_ref=external_ref,
        jurisdiction="US",
        risk_index=70,
    )


def test_list_investigations_returns_link_counts_exposure_and_assignee() -> None:
    case = make_case()
    analyst = Analyst(
        id=uuid4(),
        name="Eleni Vance",
        analyst_code="AN-8902",
        role="Senior Analyst",
        email="eleni.vance@example.com",
    )
    session = FakeSession(
        scalar=1,
        results=[
            FakeResult(
                [(case, analyst, 2, Decimal("1250.00"))],
            )
        ],
    )

    response = asyncio.run(
        list_investigations(
            db=session,  # type: ignore[arg-type]
            status_filter=None,
            search="INV-2026",
            page=1,
            page_size=10,
        )
    )

    assert response.total == 1
    assert response.items[0].linked_alerts == 2
    assert response.items[0].combined_exposure == Decimal("1250.00")
    assert response.items[0].assignee is not None
    assert response.items[0].assignee.analyst_code == "AN-8902"


def test_investigation_stats_reports_open_assigned_and_resolution() -> None:
    session = FakeSession(
        results=[FakeResult(one=(12, 8, 3, 3600.0))],
    )

    stats = asyncio.run(investigation_stats(db=session))  # type: ignore[arg-type]

    assert stats.open_count == 8
    assert stats.total_count == 12
    assert stats.assigned_to_me == 3
    assert stats.avg_resolution_time_seconds == 3600.0


def test_create_investigation_links_alerts() -> None:
    transaction_id = uuid4()
    alert = make_alert(transaction_id)
    analyst_id = uuid4()
    analyst = Analyst(
        id=analyst_id,
        name="Eleni Vance",
        analyst_code="AN-8902",
        role="Senior Analyst",
        email="eleni.vance@example.com",
    )
    session = FakeSession(
        results=[
            FakeResult([alert]),
            FakeResult([(transaction_id, Decimal("450.00"))]),
        ],
        analysts=[analyst],
    )

    created = asyncio.run(
        create_investigation(
            InvestigationCreate(
                title="Suspicious wire",
                alert_ids=[alert.id],
                assignee_id=analyst_id,
            ),
            db=session,  # type: ignore[arg-type]
        )
    )

    assert created.status == "open"
    assert created.linked_alerts == 1
    assert created.combined_exposure == Decimal("450.00")
    assert created.assignee is not None
    assert any(isinstance(item, CaseAlert) for item in session.added)
    assert alert.case_id == created.id


def test_investigation_graph_returns_typed_connections() -> None:
    investigation = make_case()
    source_id, target_id = uuid4(), uuid4()
    accounts = [
        make_account(source_id, "ACCT-1001"),
        make_account(target_id, "ACCT-1002"),
    ]
    now = datetime.now(UTC)
    session = FakeSession(
        cases=[investigation],
        accounts=accounts,
        results=[
            FakeResult([(uuid4(), source_id, target_id, Decimal("300.00"), now)]),
            FakeResult(accounts),
            FakeResult([(source_id, target_id, "198.51.100.2", now)]),
            FakeResult([(source_id, target_id, uuid4(), now)]),
        ],
    )

    graph = asyncio.run(
        investigation_graph(investigation.id, db=session),  # type: ignore[arg-type]
    )

    assert len(graph.nodes) == 2
    assert {edge.type for edge in graph.edges} == {
        "fund_transfer",
        "shared_ip",
        "shared_device",
    }
    assert graph.edges[0].amount == Decimal("300.00")
    assert len(graph.connections) == len(graph.edges)
