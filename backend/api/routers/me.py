from uuid import UUID

from fastapi import APIRouter

from shared.schemas import AnalystRead

router = APIRouter(tags=["analysts"])


@router.get("/me", response_model=AnalystRead)
async def current_analyst() -> AnalystRead:
    return AnalystRead(
        id=UUID(int=0),
        name="Eleni Vance",
        analyst_code="AN-8902",
        role="Senior Analyst",
        email="eleni.vance@example.com",
    )
