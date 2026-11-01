from collections.abc import AsyncIterator
from typing import cast
from uuid import uuid4

import jwt
import pytest
from argon2 import PasswordHasher
from fastapi import FastAPI
from fastapi.testclient import TestClient
from redis.asyncio import Redis

from api import auth as auth_module
from api import main as api_main
from api.config import AppSettings
from api.database import get_session
from api.main import app
from api.models import Analyst, AuditLog

TEST_SECRET = "test-secret-key-for-authentication-0123456789"


class FakeAuthSession:
    def __init__(self, analyst: Analyst) -> None:
        self.analyst = analyst
        self.audit_rows: list[AuditLog] = []

    async def scalar(self, _statement: object) -> Analyst:
        return self.analyst

    def add(self, row: AuditLog) -> None:
        self.audit_rows.append(row)

    async def commit(self) -> None:
        return None


class FakeRedis:
    def __init__(self) -> None:
        self.revoked: set[str] = set()

    async def get(self, key: str) -> str | None:
        return "1" if key.removeprefix("auth:revoked:") in self.revoked else None

    async def set(self, key: str, _value: str, *, ex: int) -> None:
        assert ex > 0
        self.revoked.add(key.removeprefix("auth:revoked:"))


def test_login_protected_access_and_logout_revoke_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def ready(_redis: Redis, _url: str) -> str:
        return "test"

    monkeypatch.setattr(api_main, "verify_redis_startup", ready)
    monkeypatch.setattr(
        auth_module,
        "get_settings",
        lambda: AppSettings(jwt_secret_key=TEST_SECRET, jwt_access_token_minutes=10),
    )
    analyst = Analyst(
        id=uuid4(),
        name="Eleni Vance",
        analyst_code="AN-8902",
        role="Senior Analyst",
        email="eleni.vance@example.com",
        password_hash=PasswordHasher().hash("strong-password-123"),
    )
    session = FakeAuthSession(analyst)

    async def session_dependency() -> AsyncIterator[FakeAuthSession]:
        yield session

    monkeypatch.setitem(app.dependency_overrides, get_session, session_dependency)
    with TestClient(app) as client:
        redis = FakeRedis()
        cast(FastAPI, client.app).state.redis = redis
        anonymous_response = client.get("/me")
        login_response = client.post(
            "/auth/login",
            json={"analyst_code": "AN-8902", "password": "strong-password-123"},
        )
        token = login_response.json()["access_token"]
        claims = jwt.decode(
            token,
            TEST_SECRET,
            algorithms=["HS256"],
            issuer="underlock-api",
        )
        protected_response = client.get("/me", headers={"Authorization": f"Bearer {token}"})
        logout_response = client.post("/auth/logout", headers={"Authorization": f"Bearer {token}"})
        revoked_response = client.get("/me", headers={"Authorization": f"Bearer {token}"})

    assert anonymous_response.status_code == 401
    assert login_response.status_code == 200
    assert login_response.json()["analyst_id"] == "AN-8902"
    assert claims["sub"] == "AN-8902"
    assert claims["analyst_id"] == "AN-8902"
    assert protected_response.status_code == 200
    assert logout_response.status_code == 200
    assert logout_response.json() == {"status": "logged_out"}
    assert revoked_response.status_code == 401
    assert [row.action for row in session.audit_rows] == ["analyst_login", "analyst_logout"]
    assert all(row.actor_id == analyst.id for row in session.audit_rows)


def test_login_rejects_invalid_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    async def ready(_redis: Redis, _url: str) -> str:
        return "test"

    monkeypatch.setattr(api_main, "verify_redis_startup", ready)
    monkeypatch.setattr(
        auth_module,
        "get_settings",
        lambda: AppSettings(jwt_secret_key=TEST_SECRET),
    )
    analyst = Analyst(
        id=uuid4(),
        name="Eleni Vance",
        analyst_code="AN-8902",
        role="Senior Analyst",
        email="eleni.vance@example.com",
        password_hash=PasswordHasher().hash("correct-password-123"),
    )
    session = FakeAuthSession(analyst)

    async def session_dependency() -> AsyncIterator[FakeAuthSession]:
        yield session

    monkeypatch.setitem(app.dependency_overrides, get_session, session_dependency)
    with TestClient(app) as client:
        response = client.post(
            "/auth/login",
            json={"analyst_code": "AN-8902", "password": "wrong-password"},
        )

    assert response.status_code == 401
    assert session.audit_rows == []
