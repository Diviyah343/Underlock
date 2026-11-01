"""Redis Streams consumer entry point."""

import asyncio
import os
import signal
import socket

import structlog
from redis.asyncio import Redis

from api.config import get_settings
from api.database import SessionFactory, engine
from api.redis_checks import RedisStartupError, verify_redis_startup
from worker.consumer import TransactionConsumer

logger = structlog.get_logger()


async def run() -> None:
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        redis_version = await verify_redis_startup(redis, settings.redis_url)
    except RedisStartupError as exc:
        await redis.aclose()
        raise SystemExit(f"Worker startup blocked: {exc}") from None
    logger.info("worker.redis_preflight_passed", redis_version=redis_version)
    consumer_name = f"{socket.gethostname()}-{os.getpid()}"
    consumer = TransactionConsumer(redis, SessionFactory, consumer_name, settings)
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def request_stop() -> None:
        logger.info("worker.shutdown_requested")
        stop_event.set()

    for signum in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(signum, request_stop)
        except NotImplementedError:
            signal.signal(signum, lambda _signum, _frame: loop.call_soon_threadsafe(request_stop))

    try:
        await consumer.run(stop_event)
    finally:
        await redis.aclose()
        await engine.dispose()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
