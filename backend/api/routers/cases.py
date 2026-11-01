from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, status

from shared.schemas import CaseCreate, CaseLinkedAccounts, CasePage, CaseRead, CaseStats

router = APIRouter(prefix="/cases", tags=["cases"])


@router.get("", response_model=CasePage)
async def list_cases() -> CasePage:
    return CasePage()


@router.post("", response_model=CaseRead, status_code=status.HTTP_201_CREATED)
async def create_case(payload: CaseCreate) -> CaseRead:
    now = datetime.now(UTC)
    return CaseRead(
        id=uuid4(),
        case_code=f"INV-{now.year}-0000",
        title=payload.title,
        status="open",
        assigned_analyst_id=payload.assigned_analyst_id,
        opened_at=now,
        last_activity_at=now,
    )


@router.get("/stats", response_model=CaseStats)
async def case_stats() -> CaseStats:
    return CaseStats()


@router.get("/{case_id}", response_model=CaseRead)
async def get_case(case_id: UUID) -> CaseRead:
    now = datetime.now(UTC)
    return CaseRead(
        id=case_id,
        case_code=f"INV-{now.year}-0000",
        title="Placeholder investigation",
        status="open",
        opened_at=now,
        last_activity_at=now,
    )


@router.get("/{case_id}/linked-accounts", response_model=CaseLinkedAccounts)
async def case_linked_accounts(case_id: UUID) -> CaseLinkedAccounts:
    _ = case_id
    return CaseLinkedAccounts()
