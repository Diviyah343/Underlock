from fastapi import APIRouter, HTTPException, Request
from redis.exceptions import RedisError
from sqlalchemy import text

from api.database import engine
from shared.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    database_status = "ok"
    redis_status = "ok"

    try:
        redis = getattr(request.app.state, "redis", None)
        if redis is None:
            raise RuntimeError("Redis client not initialized")
        await redis.ping()
    except (AttributeError, OSError, RedisError, RuntimeError, TimeoutError):
        redis_status = "error"

    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except (OSError, TimeoutError, RuntimeError):
        database_status = "error"

    overall_status = "ok" if database_status == "ok" and redis_status == "ok" else "degraded"
    if overall_status == "degraded":
        raise HTTPException(
            status_code=503,
            detail={
                "status": overall_status,
                "database": database_status,
                "redis": redis_status,
            },
        )

    return HealthResponse(status=overall_status, database=database_status, redis=redis_status)
