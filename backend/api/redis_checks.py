"""Shared Redis startup checks for Streams-backed services."""

from uuid import uuid4

from redis.asyncio import Redis
from redis.exceptions import RedisError


class RedisStartupError(RuntimeError):
    """Raised when Redis is unavailable or lacks the required Streams support."""


def _version_tuple(version: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in version.split(".")[:3])
    except ValueError as exc:
        raise RedisStartupError(f"Redis returned an unrecognized version: {version!r}") from exc


async def check_redis_version(redis: Redis, redis_url: str) -> str:
    try:
        info = await redis.info("server")
    except (RedisError, OSError, TimeoutError) as exc:
        raise RedisStartupError(f"Cannot reach Redis at {redis_url}: {exc}") from None

    version = str(info.get("redis_version", "unknown"))
    if _version_tuple(version) < (6, 0):
        raise RedisStartupError(
            f"Redis at {redis_url} is version {version}; Redis 6 or newer is required. "
            "Start the Redis 7 service with `docker compose up -d redis`."
        )
    return version


async def check_redis_streams(redis: Redis, redis_url: str) -> None:
    stream = f"underlock:preflight:{uuid4().hex}"
    group = f"preflight-{uuid4().hex}"
    group_created = False
    try:
        await redis.xadd(stream, {"check": "1"})
        await redis.xgroup_create(stream, group, id="0")
        group_created = True
    except (RedisError, OSError, TimeoutError) as exc:
        raise RedisStartupError(
            f"Redis at {redis_url} does not support Streams (XADD/XGROUP failed): {exc}. "
            "Use the Redis 7 service from `docker compose up -d redis`."
        ) from None
    finally:
        if group_created:
            try:
                await redis.xgroup_destroy(stream, group)
            except RedisError:
                pass
        try:
            await redis.delete(stream)
        except RedisError:
            pass


async def verify_redis_startup(redis: Redis, redis_url: str) -> str:
    version = await check_redis_version(redis, redis_url)
    await check_redis_streams(redis, redis_url)
    return version