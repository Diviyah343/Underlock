from fastapi import APIRouter

from app.mock_data import alerts
from app.models.schemas import Alert

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("", response_model=list[Alert])
def list_alerts() -> list[Alert]:
    return alerts
