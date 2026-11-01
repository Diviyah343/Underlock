import pytest
from fastapi.testclient import TestClient
from redis.asyncio import Redis

from api import main as api_main
from api.auth import AnalystPrincipal, require_analyst
from api.config import AppSettings
from api.main import app
from api.routers import health as health_router


class FakeDBConnection:
    async def __aenter__(self) -> "FakeDBConnection":
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False

    async def execute(self, *_args: object, **_kwargs: object) -> object:
        return object()


class FakeRedisClient:
    async def ping(self) -> bool:
        return True


def test_health_returns_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    async def ready(_redis: Redis, _url: str) -> str:
        return "test"

    monkeypatch.setattr(api_main, "verify_redis_startup", ready)
    monkeypatch.setitem(
        app.dependency_overrides,
        require_analyst,
        lambda: AnalystPrincipal("AN-8902", "test-token", 2_000_000_000),
    )
    monkeypatch.setattr(
        health_router,
        "engine",
        type("Engine", (), {"connect": lambda *_args, **_kwargs: FakeDBConnection()})(),
    )
    with TestClient(app) as client:
        client.app.state.redis = FakeRedisClient()
        response = client.get("/health")
        cors_response = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok", "redis": "ok"}
    assert response.headers.get("X-Request-ID")
    assert cors_response.status_code == 200
    assert cors_response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_cors_origins_are_configurable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_CORS_ORIGINS", '["https://demo.example"]')

    assert AppSettings(_env_file=None).api_cors_origins == ["https://demo.example"]
