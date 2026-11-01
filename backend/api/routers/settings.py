from fastapi import APIRouter

from shared.schemas import SettingsRead, SettingsUpdate

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=SettingsRead)
async def get_settings() -> SettingsRead:
    return SettingsRead()


@router.put("", response_model=SettingsRead)
async def update_settings(payload: SettingsUpdate) -> SettingsRead:
    return SettingsRead(**payload.model_dump())


@router.post("/reset", response_model=SettingsRead)
async def reset_settings() -> SettingsRead:
    return SettingsRead()
