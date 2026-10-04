from fastapi import APIRouter

from app.mock_data import transactions
from app.models.schemas import Transaction

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.get("", response_model=list[Transaction])
def list_transactions() -> list[Transaction]:
    return transactions
