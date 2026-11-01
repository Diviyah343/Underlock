"""Live PostgreSQL/Redis integration tests; run with `make test-integration`."""

import asyncio
import json
import os
import signal
from collections.abc import AsyncIterator, Iterator, Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from redis.asyncio import Redis
from sqlalchemy import delete, func, select

from api.auth import AnalystPrincipal, require_analyst
from api.config import get_settings
from api.database import SessionFactory
from api.main import app
from api.models import Account, AccountLink, SimulationLabel, Transaction
from shared.schemas import IngestTransaction
from worker import consumer as consumer_module
from worker.consumer import STREAM, TransactionConsumer

pytestmark = pytest.mark.integration


class LiveServices:
    def __init__(self, redis: Redis, group: str) -> None:
        self.redis = redis
        self.group = group
        self.stream_ids: list[str] = []
        self.dlq_ids: list[str] = []
        self.idempotency_keys: list[str] = []
        self.account_ids: set[UUID] = set()

    async def cleanup(self) -> None:
        await self.redis.xgroup_destroy(STREAM, self.group)
        if self.stream_ids:
            await self.redis.xdel(STREAM, *self.stream_ids)
        if self.dlq_ids:
            await self.redis.xdel("transactions:dlq", *self.dlq_ids)
        async with SessionFactory.begin() as session:
            if self.account_ids:
                await session.execute(
                    delete(AccountLink).where(
                        AccountLink.source_account_id.in_(self.account_ids)
                        | AccountLink.target_account_id.in_(self.account_ids)
                    )
                )
            if self.idempotency_keys:
                await session.execute(
                    delete(SimulationLabel).where(
                        SimulationLabel.idempotency_key.in_(self.idempotency_keys)
                    )
                )
                await session.execute(
                    delete(Transaction).where(
                        Transaction.idempotency_key.in_(self.idempotency_keys)
                    )
                )
            if self.account_ids:
                await session.execute(delete(Account).where(Account.id.in_(self.account_ids)))
        await self.redis.aclose()


@pytest_asyncio.fixture
async def live_services(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[LiveServices]:
    redis = Redis.from_url(get_settings().redis_url, decode_responses=True)
    group = f"integration-{uuid4().hex}"
    monkeypatch.setattr(consumer_module, "GROUP", group)
    services = LiveServices(redis, group)
    group_created = False
    try:
        await redis.xgroup_create(STREAM, group, id="$", mkstream=True)
        group_created = True
        yield services
    finally:
        if group_created:
            await services.cleanup()
        else:
            await redis.aclose()


@pytest.fixture
def live_api_client() -> Iterator[TestClient]:
    app.dependency_overrides[require_analyst] = lambda: AnalystPrincipal(
        "AN-8902", "integration-token", 2_000_000_000
    )
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.pop(require_analyst, None)


def _transaction_body(account_id: UUID | None = None) -> dict[str, Any]:
    return {
        "tx_hash": f"integration-{uuid4().hex}",
        "account_id": str(account_id or uuid4()),
        "amount": "84.25",
        "currency": "USD",
        "jurisdiction": "US",
        "direction": "inflow",
        "tx_type": "PAYMENT",
        "occurred_at": datetime.now(UTC).isoformat(),
    }


def _consumer(services: LiveServices, *, idle_ms: int = 0) -> TransactionConsumer:
    settings = get_settings().model_copy(update={"worker_min_idle_ms": idle_ms})
    return TransactionConsumer(
        services.redis,
        SessionFactory,
        f"integration-{uuid4().hex}",
        settings,
    )


async def _read_new(services: LiveServices, consumer_name: str) -> list[tuple[str, dict[str, str]]]:
    response = await services.redis.xreadgroup(
        services.group,
        consumer_name,
        {STREAM: ">"},
        count=1000,
        block=100,
    )
    entries = TransactionConsumer._flatten(response)
    services.stream_ids.extend(message_id for message_id, _fields in entries)
    return entries


async def _transaction_count(idempotency_key: str) -> int:
    async with SessionFactory() as session:
        return int(
            await session.scalar(
                select(func.count()).select_from(Transaction).where(
                    Transaction.idempotency_key == idempotency_key
                )
            )
            or 0
        )


async def test_live_idempotency_persists_one_row_and_stream_entry(
    live_services: LiveServices,
    live_api_client: TestClient,
) -> None:
    key = f"integration-idem-{uuid4().hex}"
    body = _transaction_body()
    account_id = UUID(body["account_id"])
    live_services.idempotency_keys.append(key)
    live_services.account_ids.add(account_id)
    before = await live_services.redis.xlen(STREAM)

    first = live_api_client.post(
        "/ingest/transactions", json=body, headers={"Idempotency-Key": key}
    )
    second = live_api_client.post(
        "/ingest/transactions", json=body, headers={"Idempotency-Key": key}
    )
    assert first.status_code == 202
    assert second.status_code == 200
    assert second.json()["duplicate_count"] == 1
    assert await live_services.redis.xlen(STREAM) == before + 1

    worker = _consumer(live_services)
    entries = await _read_new(live_services, worker.consumer_name)
    assert len(entries) == 1
    await worker.process_entries(entries)
    assert await _transaction_count(key) == 1


async def test_claimed_message_recovers_after_post_commit_crash(
    live_services: LiveServices,
    live_api_client: TestClient,
) -> None:
    key = f"integration-crash-{uuid4().hex}"
    body = _transaction_body()
    account_id = UUID(body["account_id"])
    live_services.idempotency_keys.append(key)
    live_services.account_ids.add(account_id)
    response = live_api_client.post(
        "/ingest/transactions", json=body, headers={"Idempotency-Key": key}
    )
    assert response.status_code == 202

    class CrashAfterCommit(TransactionConsumer):
        async def persist_batch(
            self,
            entries: Sequence[tuple[str, dict[str, str], IngestTransaction, datetime]],
        ) -> tuple[list[dict[str, str]], int]:
            await super().persist_batch(entries)
            raise RuntimeError("injected crash after database commit")

    first_worker = CrashAfterCommit(
        live_services.redis,
        SessionFactory,
        f"first-{uuid4().hex}",
        get_settings().model_copy(update={"worker_min_idle_ms": 0}),
    )
    entries = await _read_new(live_services, first_worker.consumer_name)
    assert len(entries) == 1
    await first_worker.process_entries(entries)
    assert await _transaction_count(key) == 1
    first_pending = await live_services.redis.xpending_range(
        STREAM, live_services.group, entries[0][0], entries[0][0], 1
    )
    assert first_pending[0]["times_delivered"] == 1

    second_worker = _consumer(live_services, idle_ms=0)
    await second_worker.reclaim_pending()
    assert await _transaction_count(key) == 1
    assert not await live_services.redis.xpending_range(
        STREAM, live_services.group, entries[0][0], entries[0][0], 1
    )


async def test_poison_message_moves_to_dlq_on_fifth_delivery(
    live_services: LiveServices,
) -> None:
    worker = _consumer(live_services, idle_ms=0)
    message_id = await live_services.redis.xadd(
        STREAM,
        {"payload": "{not-json", "ingested_at": datetime.now(UTC).isoformat()},
    )
    live_services.stream_ids.append(message_id)
    first_delivery = await _read_new(live_services, worker.consumer_name)
    await worker.process_entries(first_delivery)

    for _ in range(4):
        await worker.reclaim_pending()

    pending = await live_services.redis.xpending_range(
        STREAM, live_services.group, message_id, message_id, 1
    )
    assert pending == []
    dead_letters = await live_services.redis.xrange("transactions:dlq")
    matches = [
        fields for _entry_id, fields in dead_letters if fields.get("source_id") == message_id
    ]
    assert len(matches) == 1
    assert matches[0]["attempts"] == "5"
    live_services.dlq_ids.extend(
        entry_id
        for entry_id, fields in dead_letters
        if fields.get("source_id") == message_id
    )


async def test_invalid_batch_returns_422_without_enqueue(
    live_services: LiveServices,
    live_api_client: TestClient,
) -> None:
    before = await live_services.redis.xlen(STREAM)
    good = _transaction_body() | {"idempotency_key": f"integration-good-{uuid4().hex}"}
    bad = _transaction_body() | {
        "idempotency_key": f"integration-bad-{uuid4().hex}",
        "amount": "0",
    }
    response = live_api_client.post("/ingest/transactions", json=[good, bad])

    assert response.status_code == 422
    assert await live_services.redis.xlen(STREAM) == before


@pytest.mark.skipif(os.name == "nt", reason="catchable SIGTERM integration test requires POSIX/WSL")
async def test_sigterm_finishes_batch_without_pending_entries(
    live_services: LiveServices,
) -> None:
    from worker.main import run as run_worker

    account_id = uuid4()
    live_services.account_ids.add(account_id)
    payloads = []
    for index in range(400):
        key = f"integration-sigterm-{uuid4().hex}"
        live_services.idempotency_keys.append(key)
        transaction = IngestTransaction.model_validate(
            _transaction_body(account_id) | {"idempotency_key": key, "tx_hash": f"sig-{index}"}
        )
        payloads.append(transaction.model_dump(mode="json"))
    ingested_at = datetime.now(UTC).isoformat()
    for payload in payloads:
        await live_services.redis.xadd(
            STREAM,
            {"payload": json.dumps(payload), "ingested_at": ingested_at},
        )

    original_handlers = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)}
    worker_task = asyncio.create_task(run_worker())
    try:
        for _ in range(500):
            async with SessionFactory() as session:
                persisted = int(
                    await session.scalar(
                        select(func.count()).select_from(Transaction).where(
                            Transaction.idempotency_key.in_(live_services.idempotency_keys)
                        )
                    )
                    or 0
                )
            if persisted:
                break
            await asyncio.sleep(0.01)
        assert persisted > 0
        os.kill(os.getpid(), signal.SIGTERM)
        await asyncio.wait_for(worker_task, timeout=10)
    finally:
        loop = asyncio.get_running_loop()
        for sig, handler in original_handlers.items():
            loop.remove_signal_handler(sig)
            signal.signal(sig, handler)
        if not worker_task.done():
            worker_task.cancel()
            await asyncio.gather(worker_task, return_exceptions=True)

    pending_summary = await live_services.redis.xpending(STREAM, live_services.group)
    assert pending_summary["pending"] == 0