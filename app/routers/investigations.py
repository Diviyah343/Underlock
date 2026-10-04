from fastapi import APIRouter

from app.mock_data import investigations
from app.models.schemas import Investigation

router = APIRouter(prefix="/investigations", tags=["investigations"])


@router.get("", response_model=list[Investigation])
def list_investigations() -> list[Investigation]:
    return investigations
