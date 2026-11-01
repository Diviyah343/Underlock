"""Async simulator CLI and simulator-label persistence."""

import argparse
import asyncio
import os
import secrets
import time
from collections.abc import Sequence

import httpx
import structlog
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import async_sessionmaker

from api.config import get_settings
from api.database import engine
from api.logging_config import configure_logging
from api.models import SimulationLabel
from simulator.generator import SimulatedTransaction, TrafficGenerator

logger = structlog.get_logger()


class AsyncTokenBucket:
    def __init__(self, rate: float, capacity: float | None = None) -> None:
        self.rate = rate
        self.capacity = max(1.0, capacity if capacity is not None else rate)
        self.tokens = 0.0
        self.updated_at = time.monotonic()

    async def acquire(self) -> None:
        while True:
            now = time.monotonic()
            elapsed = now - self.updated_at
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
            self.updated_at = now
            if self.tokens >= 1:
                self.tokens -= 1
                return
            await asyncio.sleep((1 - self.tokens) / self.rate)


async def _send_batch(
    client: httpx.AsyncClient,
    api_url: str,
    batch: Sequence[SimulatedTransaction],
    analyst_code: str,
    analyst_password: str,
) -> None:
    body = [item.transaction.model_dump(mode="json") for item in batch]
    delay = 1.0
    access_token = await _login(client, api_url, analyst_code, analyst_password)
    while True:
        try:
            response = await client.post(
                f"{api_url.rstrip('/')}/ingest/transactions",
                json=body,
                headers={"Authorization": f"Bearer {access_token}"},
            )
        except httpx.TransportError:
            logger.exception("simulator.api_unavailable", retry_in_seconds=delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 15)
            continue
        if response.status_code == 401:
            access_token = await _login(client, api_url, analyst_code, analyst_password)
            continue
        if response.status_code == 503:
            retry_after = response.headers.get("Retry-After")
            await asyncio.sleep(float(retry_after) if retry_after else delay)
            delay = min(delay * 2, 15)
            continue
        response.raise_for_status()
        logger.info(
            "simulator.batch_sent",
            transactions=len(batch),
            accepted=response.json()["accepted_count"],
            duplicates=response.json()["duplicate_count"],
        )
        return


async def _login(
    client: httpx.AsyncClient,
    api_url: str,
    analyst_code: str,
    analyst_password: str,
) -> str:
    response = await client.post(
        f"{api_url.rstrip('/')}/auth/login",
        json={"analyst_code": analyst_code, "password": analyst_password},
    )
    response.raise_for_status()
    return response.json()["access_token"]


async def _write_labels(batch: Sequence[SimulatedTransaction]) -> None:
    rows = [
        {
            "idempotency_key": item.transaction.idempotency_key,
            "is_fraud": item.is_fraud,
            "pattern": item.pattern.value if item.pattern else None,
        }
        for item in batch
    ]
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory.begin() as session:
        statement = pg_insert(SimulationLabel).values(rows)
        await session.execute(
            statement.on_conflict_do_update(
                index_elements=[SimulationLabel.idempotency_key],
                set_={
                    "is_fraud": statement.excluded.is_fraud,
                    "pattern": statement.excluded.pattern,
                },
            )
        )


async def simulate(args: argparse.Namespace) -> None:
    if not args.analyst_code or not args.analyst_password:
        raise ValueError(
            "SIMULATOR_ANALYST_CODE and SIMULATOR_ANALYST_PASSWORD must be configured"
        )
    settings = get_settings()
    configure_logging(settings.log_level)
    seed = args.seed if args.seed is not None else secrets.randbits(32)
    logger.info("simulator.started", seed=seed, rate=args.rate, fraud_rate=args.fraud_rate)
    generator = TrafficGenerator(seed, args.accounts, args.rate, args.fraud_rate)
    bucket = AsyncTokenBucket(args.rate)
    start = time.monotonic()
    batch: list[SimulatedTransaction] = []
    sent_count = 0

    async with httpx.AsyncClient(timeout=10) as client:
        while args.duration == 0 or time.monotonic() - start < args.duration:
            await bucket.acquire()
            batch.append(generator.generate())
            if len(batch) >= args.batch_size:
                await _send_batch(
                    client,
                    args.api_url,
                    batch,
                    args.analyst_code,
                    args.analyst_password,
                )
                await _write_labels(batch)
                sent_count += len(batch)
                batch.clear()

        if batch:
            await _send_batch(
                client,
                args.api_url,
                batch,
                args.analyst_code,
                args.analyst_password,
            )
            await _write_labels(batch)
            sent_count += len(batch)

    await engine.dispose()
    logger.info("simulator.finished", transactions=sent_count, seed=seed)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate seeded PaySim-style traffic")
    parser.add_argument("--rate", type=float, default=5, help="target transactions per second")
    parser.add_argument("--duration", type=float, default=0, help="seconds; 0 runs forever")
    parser.add_argument("--fraud-rate", type=float, default=0.10)
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="reproducible data seed; a fresh random seed is chosen when omitted",
    )
    parser.add_argument("--api-url", default=os.getenv("API_URL", "http://localhost:8000"))
    parser.add_argument("--analyst-code", default=os.getenv("SIMULATOR_ANALYST_CODE", ""))
    parser.add_argument("--analyst-password", default=os.getenv("SIMULATOR_ANALYST_PASSWORD", ""))
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--accounts", type=int, default=2000)
    args = parser.parse_args(argv)
    if args.rate <= 0:
        parser.error("--rate must be greater than zero")
    if args.duration < 0:
        parser.error("--duration cannot be negative")
    if not 0 <= args.fraud_rate <= 1:
        parser.error("--fraud-rate must be between 0 and 1")
    if not 1 <= args.batch_size <= 500:
        parser.error("--batch-size must be between 1 and 500")
    if args.accounts < 4:
        parser.error("--accounts must be at least 4 for multi-hop scenarios")
    return args


def main() -> None:
    asyncio.run(simulate(parse_args()))


if __name__ == "__main__":
    main()
