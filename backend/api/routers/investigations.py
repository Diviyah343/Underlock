from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated, cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.selectable import ScalarSelect

from api.database import get_session
from api.models import Account, Alert, Analyst, Case, CaseAlert, Transaction
from shared.constants import CaseStatus
from shared.schemas import (
    AnalystRead,
    InvestigationCreate,
    InvestigationGraph,
    InvestigationGraphEdge,
    InvestigationGraphNode,
    InvestigationPage,
    InvestigationRead,
    InvestigationStats,
)

router = APIRouter(prefix="/investigations", tags=["investigations"])
SessionDependency = Annotated[AsyncSession, Depends(get_session)]


def _case_filters(
    status_filter: CaseStatus | None,
    search: str | None,
) -> list[ColumnElement[bool]]:
    filters: list[ColumnElement[bool]] = []
    if status_filter is not None:
        filters.append(Case.status == status_filter)
    if search and search.strip():
        term = f"%{search.strip().lower()}%"
        filters.append(
            or_(
                func.lower(Case.case_code).like(term),
                func.lower(Case.title).like(term),
            )
        )
    return filters


def _assignee_read(analyst: Analyst | None) -> AnalystRead | None:
    if analyst is None:
        return None
    return AnalystRead(
        id=analyst.id,
        name=analyst.name,
        analyst_code=analyst.analyst_code,
        role=analyst.role,
        email=analyst.email,
    )


def _exposure_subquery() -> ScalarSelect[Decimal]:
    linked_transactions = (
        select(Transaction.id.label("transaction_id"), Transaction.amount.label("amount"))
        .join(Alert, Alert.transaction_id == Transaction.id)
        .join(CaseAlert, CaseAlert.alert_id == Alert.id)
        .where(CaseAlert.case_id == Case.id)
        .distinct()
        .correlate(Case)
        .subquery()
    )
    return (
        select(func.coalesce(func.sum(linked_transactions.c.amount), Decimal("0")))
        .scalar_subquery()
    )


@router.get("", response_model=InvestigationPage)
async def list_investigations(
    db: SessionDependency,
    status_filter: Annotated[CaseStatus | None, Query(alias="status")] = None,
    search: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, alias="pageSize", ge=1, le=100),
) -> InvestigationPage:
    filters = _case_filters(status_filter, search)
    total_stmt = select(func.count(Case.id))
    if filters:
        total_stmt = total_stmt.where(*filters)
    total = int(await db.scalar(total_stmt) or 0)

    linked_alert_count = (
        select(func.count(CaseAlert.alert_id))
        .where(CaseAlert.case_id == Case.id)
        .correlate(Case)
        .scalar_subquery()
    )
    stmt = (
        select(Case, Analyst, linked_alert_count, _exposure_subquery())
        .outerjoin(Analyst, Analyst.id == Case.assigned_analyst_id)
        .order_by(Case.last_activity_at.desc(), Case.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    if filters:
        stmt = stmt.where(*filters)
    result = await db.execute(stmt)

    investigation_rows = cast(
        list[tuple[Case, Analyst | None, int, Decimal]],
        result.all(),
    )
    items = [
        InvestigationRead(
            id=case.id,
            case_code=case.case_code,
            title=case.title,
            status=case.status,
            linked_alerts=alert_count,
            combined_exposure=exposure,
            assignee=_assignee_read(analyst),
            last_activity=case.last_activity_at,
            created_at=case.opened_at,
            closed_at=case.closed_at,
        )
        for case, analyst, alert_count, exposure in investigation_rows
    ]
    return InvestigationPage(items=items, total=total, page=page, page_size=page_size)


@router.get("/stats", response_model=InvestigationStats)
async def investigation_stats(db: SessionDependency) -> InvestigationStats:
    totals = await db.execute(
        select(
            func.count(Case.id),
            func.count(Case.id).filter(Case.status != CaseStatus.CLOSED),
            func.count(Case.id).filter(Case.assigned_analyst_id == Analyst.id),
            func.avg(func.extract("epoch", Case.closed_at - Case.opened_at)).filter(
                Case.status == CaseStatus.CLOSED,
                Case.closed_at.is_not(None),
            ),
        )
        .select_from(Case)
        .outerjoin(Analyst, Analyst.analyst_code == "AN-8902")
    )
    total_count, open_count, assigned_to_me, avg_resolution_seconds = cast(
        tuple[int, int, int, Decimal | float | None],
        totals.one(),
    )
    return InvestigationStats(
        open_count=open_count,
        total_count=total_count,
        assigned_to_me=assigned_to_me,
        avg_resolution_time_seconds=float(avg_resolution_seconds or 0),
    )


@router.post("", response_model=InvestigationRead, status_code=status.HTTP_201_CREATED)
async def create_investigation(
    payload: InvestigationCreate,
    db: SessionDependency,
) -> InvestigationRead:
    alert_ids = list(dict.fromkeys(payload.alert_ids))
    async with db.begin():
        alerts_result = await db.execute(select(Alert).where(Alert.id.in_(alert_ids)))
        alerts = list(alerts_result.scalars().all())
        if len(alerts) != len(alert_ids):
            raise HTTPException(status_code=404, detail="One or more alerts were not found")

        analyst: Analyst | None = None
        if payload.assignee_id is not None:
            analyst = await db.get(Analyst, payload.assignee_id)
            if analyst is None:
                raise HTTPException(status_code=404, detail="Assignee not found")

        now = datetime.now(UTC)
        case = Case(
            case_code=f"INV-{now.year}-{uuid4().hex[:8].upper()}",
            title=payload.title.strip(),
            status=CaseStatus.OPEN,
            assigned_analyst_id=payload.assignee_id,
            opened_at=now,
            last_activity_at=now,
        )
        db.add(case)
        await db.flush()
        for alert in alerts:
            db.add(CaseAlert(case_id=case.id, alert_id=alert.id))
            if alert.case_id is None:
                alert.case_id = case.id
        linked_transaction_rows = await db.execute(
            select(Transaction.id, Transaction.amount)
            .join(Alert, Alert.transaction_id == Transaction.id)
            .where(Alert.id.in_(alert_ids))
            .distinct()
        )
        combined_exposure = sum(
            (amount for _transaction_id, amount in linked_transaction_rows.all()),
            Decimal("0"),
        )

    return InvestigationRead(
        id=case.id,
        case_code=case.case_code,
        title=case.title,
        status=case.status,
        linked_alerts=len(alerts),
        combined_exposure=combined_exposure,
        assignee=_assignee_read(analyst),
        last_activity=case.last_activity_at,
        created_at=case.opened_at,
        closed_at=case.closed_at,
    )


@router.get("/{investigation_id}/graph", response_model=InvestigationGraph)
async def investigation_graph(
    investigation_id: UUID,
    db: SessionDependency,
) -> InvestigationGraph:
    case = await db.get(Case, investigation_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Investigation not found")

    linked_transactions_result = await db.execute(
        select(
            Transaction.id,
            Transaction.account_id,
            Transaction.counterparty_account_id,
            Transaction.amount,
            Transaction.occurred_at,
        )
        .join(Alert, Alert.transaction_id == Transaction.id)
        .join(CaseAlert, CaseAlert.alert_id == Alert.id)
        .where(CaseAlert.case_id == investigation_id)
    )
    linked_transactions = cast(
        list[tuple[UUID, UUID, UUID | None, Decimal, datetime]],
        linked_transactions_result.all(),
    )
    account_ids = {
        account_id
        for _transaction_id, source_id, target_id, _amount, _occurred_at in linked_transactions
        for account_id in (source_id, target_id)
        if account_id is not None
    }
    if not account_ids:
        return InvestigationGraph()

    accounts_result = await db.execute(select(Account).where(Account.id.in_(account_ids)))
    accounts = list(accounts_result.scalars().all())
    nodes = [
        InvestigationGraphNode(
            id=account.id,
            external_ref=account.external_ref,
            name=account.name,
        )
        for account in accounts
    ]

    transfer_totals: dict[tuple[UUID, UUID], tuple[int, Decimal, datetime]] = {}
    for _transaction_id, source_id, target_id, amount, occurred_at in linked_transactions:
        if target_id is None or source_id == target_id:
            continue
        pair = (source_id, target_id)
        count, total_amount, last_seen = transfer_totals.get(
            pair, (0, Decimal("0"), occurred_at)
        )
        transfer_totals[pair] = (
            count + 1,
            total_amount + amount,
            max(last_seen, occurred_at),
        )

    edges = [
        InvestigationGraphEdge(
            source=source,
            target=target,
            type="fund_transfer",
            transaction_count=count,
            amount=amount,
            last_seen_at=last_seen,
        )
        for (source, target), (count, amount, last_seen) in transfer_totals.items()
    ]

    cutoff = datetime.now(UTC) - timedelta(days=30)
    left_ip = Transaction.__table__.alias("shared_ip_left")
    right_ip = Transaction.__table__.alias("shared_ip_right")
    shared_ip_result = await db.execute(
        select(
            left_ip.c.account_id,
            right_ip.c.account_id,
            left_ip.c.ip_address,
            func.max(func.greatest(left_ip.c.occurred_at, right_ip.c.occurred_at)),
        )
        .select_from(
            left_ip.join(
                right_ip,
                and_(
                    left_ip.c.ip_address == right_ip.c.ip_address,
                    left_ip.c.account_id < right_ip.c.account_id,
                ),
            )
        )
        .where(
            left_ip.c.ip_address.is_not(None),
            left_ip.c.occurred_at >= cutoff,
            right_ip.c.occurred_at >= cutoff,
            left_ip.c.account_id.in_(account_ids),
            right_ip.c.account_id.in_(account_ids),
        )
        .group_by(left_ip.c.account_id, right_ip.c.account_id, left_ip.c.ip_address)
    )
    ip_connections = cast(
        list[tuple[UUID, UUID, str, datetime]],
        shared_ip_result.all(),
    )
    for source, target, shared_value, last_seen in ip_connections:
        edges.append(
            InvestigationGraphEdge(
                source=source,
                target=target,
                type="shared_ip",
                shared_value=shared_value,
                last_seen_at=last_seen,
            )
        )

    left_device = Transaction.__table__.alias("shared_device_left")
    right_device = Transaction.__table__.alias("shared_device_right")
    shared_device_result = await db.execute(
        select(
            left_device.c.account_id,
            right_device.c.account_id,
            left_device.c.device_id,
            func.max(func.greatest(left_device.c.occurred_at, right_device.c.occurred_at)),
        )
        .select_from(
            left_device.join(
                right_device,
                and_(
                    left_device.c.device_id == right_device.c.device_id,
                    left_device.c.account_id < right_device.c.account_id,
                ),
            )
        )
        .where(
            left_device.c.device_id.is_not(None),
            left_device.c.occurred_at >= cutoff,
            right_device.c.occurred_at >= cutoff,
            left_device.c.account_id.in_(account_ids),
            right_device.c.account_id.in_(account_ids),
        )
        .group_by(
            left_device.c.account_id,
            right_device.c.account_id,
            left_device.c.device_id,
        )
    )
    device_connections = cast(
        list[tuple[UUID, UUID, UUID, datetime]],
        shared_device_result.all(),
    )
    for source, target, shared_device_id, last_seen in device_connections:
        edges.append(
            InvestigationGraphEdge(
                source=source,
                target=target,
                type="shared_device",
                shared_value=str(shared_device_id),
                last_seen_at=last_seen,
            )
        )

    return InvestigationGraph(nodes=nodes, edges=edges, connections=edges)
