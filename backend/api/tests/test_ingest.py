import json
from typing import Any, cast
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from redis.asyncio import Redis
from redis.exceptions import RedisError

from api import main as api_main
from api.auth import AnalystPrincipal, require_analyst
from api.main import app
from shared.schemas import TransactionIngestPayload


class FakeRedis:
    def __init__(self) -> None:
        self.idempotency: dict[str, str] = {}
        self.messages: list[dict[str, str]] = []

    async def eval(self, _script: str, numkeys: int, stream: str, *args: str) -> list[str]:
        assert numkeys == 1
        assert stream == "transactions"
        results: list[str] = []
        for index in range(0, len(args), 3):
            key, payload_json, ingested_at = args[index : index + 3]
            if key in self.idempotency:
                results.extend((self.idempotency[key], "1"))
                continue
            self.idempotency[key] = "accepted"
            self.messages.append(
                {
                    "payload": payload_json,
                    "ingested_at": ingested_at,
                }
            )
            results.extend(("accepted", "0"))
        return results


class DownRedis:
    async def eval(self, *_args: object) -> list[str]:
        raise RedisError("redis unavailable")


@pytest.fixture(autouse=True)
def bypass_redis_startup_check(monkeypatch: pytest.MonkeyPatch) -> None:
    async def ready(_redis: Redis, _url: str) -> str:
        return "test"

    monkeypatch.setattr(api_main, "verify_redis_startup", ready)
    monkeypatch.setitem(
        app.dependency_overrides,
        require_analyst,
        lambda: AnalystPrincipal("AN-8902", "test-token", 2_000_000_000),
    )


def transaction_body() -> dict[str, Any]:
    return {
        "tx_hash": "hash-1",
        "account_id": str(uuid4()),
        "amount": "120.50",
        "currency": "USD",
        "jurisdiction": "US",
        "direction": "outflow",
        "tx_type": "TRANSFER",
        "occurred_at": "2025-01-01T12:00:00Z",
    }


def test_single_ingest_and_duplicate_are_idempotent() -> None:
    fake_redis = FakeRedis()
    with TestClient(app) as client:
        cast(FastAPI, client.app).state.redis = fake_redis
        first = client.post(
            "/ingest/transactions",
            json=transaction_body(),
            headers={"Idempotency-Key": "single-1"},
        )
        second = client.post(
            "/ingest/transactions",
            json=transaction_body(),
            headers={"Idempotency-Key": "single-1"},
        )
        missing_header = client.post("/ingest/transactions", json=transaction_body())

    assert first.status_code == 202
    assert first.json()["accepted_count"] == 1
    assert second.status_code == 200
    assert second.json()["duplicate_count"] == 1
    assert second.json()["items"][0]["status"] == "accepted"
    assert missing_header.status_code == 422
    assert len(fake_redis.messages) == 1


def test_redis_outage_returns_retryable_service_unavailable() -> None:
    with TestClient(app) as client:
        cast(FastAPI, client.app).state.redis = DownRedis()
        response = client.post(
            "/ingest/transactions",
            json=transaction_body(),
            headers={"Idempotency-Key": "retry-me"},
        )

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "1"


def test_batch_ingest_requires_item_keys_and_valid_payloads() -> None:
    fake_redis = FakeRedis()
    first_body = transaction_body() | {"idempotency_key": "batch-1"}
    second_body = transaction_body() | {"idempotency_key": "batch-2", "tx_hash": "hash-2"}
    with TestClient(app) as client:
        cast(FastAPI, client.app).state.redis = fake_redis
        response = client.post("/ingest/transactions", json=[first_body, second_body])
        invalid = client.post(
            "/ingest/transactions",
            json=transaction_body() | {"is_fraud": True},
            headers={"Idempotency-Key": "single-2"},
        )

    assert response.status_code == 202
    assert response.json()["accepted_count"] == 2
    assert invalid.status_code == 422
    assert len(fake_redis.messages) == 2
    assert all("is_fraud" not in json.loads(row["payload"]) for row in fake_redis.messages)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("amount", "0"),
        ("tx_type", "WIRE"),
        ("direction", "sideways"),
        ("tx_hash", "  "),
        ("occurred_at", "not-a-timestamp"),
        ("occurred_at", "2025-01-01T12:00:00"),
        ("occurred_at", 1735732800),
    ],
)
def test_ingest_schema_rejects_invalid_values(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        TransactionIngestPayload.model_validate(transaction_body() | {field: value})
