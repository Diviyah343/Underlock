from fastapi import APIRouter

from app import mock_data
from app.models.schemas import DashboardSettings

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=DashboardSettings)
def get_settings() -> DashboardSettings:
    return mock_data.dashboard_settings


@router.put("", response_model=DashboardSettings)
def update_settings(updated_settings: DashboardSettings) -> DashboardSettings:
    mock_data.dashboard_settings = updated_settings
    return mock_data.dashboard_settings
