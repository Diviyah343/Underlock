"""Validate configured Redis, PostgreSQL, migrations, and seed data."""

import asyncio
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from redis.asyncio import Redis
from sqlalchemy import select, text

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from api.config import get_settings  # noqa: E402
from api.database import engine  # noqa: E402
from api.models import Rule  # noqa: E402
from api.redis_checks import check_redis_streams, check_redis_version  # noqa: E402
from api.seed import RULES  # noqa: E402


async def run_check(
    label: str,
    check: Callable[[], Awaitable[str]],
    fix: str,
) -> bool:
    try:
        detail = await check()
    except Exception as exc:
        print(f"FAIL {label}: {exc}\n  Fix: {fix}")
        return False
    print(f"PASS {label}: {detail}")
    return True


async def main() -> int:
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    outcomes: list[bool] = []

    async def redis_version() -> str:
        return await check_redis_version(redis, settings.redis_url)

    async def redis_streams() -> str:
        await check_redis_streams(redis, settings.redis_url)
        return "XADD and XGROUP CREATE succeeded; probe stream was removed"

    async def postgres_connection() -> str:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        return f"connected using {settings.database_url}"

    async def alembic_head() -> str:
        config = Config(str(BACKEND_ROOT / "alembic.ini"))
        script = ScriptDirectory.from_config(config)
        expected = script.get_current_head()
        async with engine.connect() as connection:
            current = await connection.run_sync(
                lambda sync_connection: MigrationContext.configure(
                    sync_connection
                ).get_current_revision()
            )
        if current != expected:
            raise RuntimeError(f"database revision is {current!r}; expected {expected!r}")
        return f"database revision {current} matches head {expected}"

    async def seed_rules() -> str:
        expected = {str(rule["key"]) for rule in RULES}
        async with engine.connect() as connection:
            actual = set((await connection.scalars(select(Rule.key))).all())
        missing = expected - actual
        if missing:
            raise RuntimeError(f"missing seed rule keys: {', '.join(sorted(missing))}")
        return f"all {len(expected)} seed rules exist"

    try:
        outcomes.append(
            await run_check(
                "Redis version",
                redis_version,
                "Run `docker compose up -d redis` and confirm REDIS_URL uses localhost:6380.",
            )
        )
        outcomes.append(
            await run_check(
                "Redis Streams",
                redis_streams,
                "Use the Redis 7 container (`docker compose up -d redis`) at localhost:6380.",
            )
        )
        outcomes.append(
            await run_check(
                "PostgreSQL connection",
                postgres_connection,
                (
                    "Run `docker compose up -d postgres` and check DATABASE_URL credentials "
                    "on localhost:5433."
                ),
            )
        )
        outcomes.append(
            await run_check(
                "Alembic head",
                alembic_head,
                "Run `uv run alembic upgrade head` against the configured DATABASE_URL.",
            )
        )
        outcomes.append(
            await run_check(
                "Seed rules",
                seed_rules,
                "Run `uv run python -m api.seed` after applying migrations.",
            )
        )
    finally:
        await redis.aclose()
        await engine.dispose()

    return 0 if all(outcomes) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))