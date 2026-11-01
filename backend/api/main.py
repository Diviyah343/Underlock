import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis

from api.auth import require_analyst
from api.auth import router as auth_router
from api.config import get_settings
from api.logging_config import configure_logging
from api.middleware import RequestIdMiddleware
from api.redis_checks import RedisStartupError, verify_redis_startup
from api.routers import alerts, cases, health, ingest, investigations, me, settings, transactions

app_settings = get_settings()
configure_logging(app_settings.log_level)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    redis = Redis.from_url(app_settings.redis_url, decode_responses=True)
    try:
        redis_version = await verify_redis_startup(redis, app_settings.redis_url)
    except RedisStartupError as exc:
        await redis.aclose()
        print(f"API startup blocked: {exc}", file=sys.stderr)
        raise RuntimeError(str(exc)) from None
    structlog.get_logger().info("api.redis_preflight_passed", redis_version=redis_version)
    application.state.redis = redis
    try:
        yield
    finally:
        await redis.aclose()


app = FastAPI(title="Underlock API", version="0.1.0", lifespan=lifespan)
app.add_middleware(RequestIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=app_settings.api_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router)
protected = [Depends(require_analyst)]
app.include_router(health.router, dependencies=protected)
app.include_router(transactions.router, dependencies=protected)
app.include_router(transactions.metrics_router, dependencies=protected)
app.include_router(alerts.router, dependencies=protected)
app.include_router(cases.router, dependencies=protected)
app.include_router(investigations.router, dependencies=protected)
app.include_router(settings.router, dependencies=protected)
app.include_router(me.router, dependencies=protected)
app.include_router(ingest.router, dependencies=protected)
