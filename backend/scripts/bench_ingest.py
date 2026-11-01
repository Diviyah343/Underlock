"""Run clean-database Redis/PostgreSQL ingestion benchmarks."""

import argparse
import asyncio
import os
import platform
import shutil
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import psutil
import structlog
from redis.asyncio import Redis
from sqlalchemy import text

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from api.config import get_settings  # noqa: E402
from api.database import engine  # noqa: E402
from simulator.cli import AsyncTokenBucket, _write_labels  # noqa: E402
from simulator.generator import SimulatedTransaction, TrafficGenerator  # noqa: E402

RESULTS_PATH = BACKEND_ROOT / "bench" / "results.md"
STREAM = "transactions"
GROUP = "workers"
logger = structlog.get_logger()


def percentile(samples: list[float], value: float) -> float | None:
    if not samples:
        return None
    ordered = sorted(samples)
    position = (len(ordered) - 1) * value
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    weight = position - low
    return ordered[low] * (1 - weight) + ordered[high] * weight


def docker_runtime() -> str:
    executable = shutil.which("docker")
    if executable is None:
        return "Docker CLI unavailable; WSL2/VM status unknown"
    result = subprocess.run(
        [executable, "info", "--format", "{{.OperatingSystem}}|{{.KernelVersion}}"],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    if result.returncode != 0:
        return "Docker command present, engine unavailable"
    detail = result.stdout.strip()
    if "WSL2" in detail.upper() or "MICROSOFT-STANDARD-WSL2" in detail.upper():
        return f"WSL2 ({detail})"
    if "DOCKER DESKTOP" in detail.upper():
        return f"Docker Desktop VM ({detail})"
    return detail


def machine_description() -> str:
    return (
        f"{platform.system()} {platform.release()}; {platform.processor()}; "
        f"{psutil.cpu_count(logical=False)} cores / {psutil.cpu_count(logical=True)} threads; "
        f"{psutil.virtual_memory().total / (1024**3):.1f} GiB RAM; Docker: {docker_runtime()}"
    )


async def clean_database_and_stream(redis: Redis) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "TRUNCATE TABLE alert_feedback, case_alerts, alerts, account_links, "
                "transactions, beneficiaries, devices, accounts, sim_labels CASCADE"
            )
        )
    if await redis.exists(STREAM):
        for group in await redis.xinfo_groups(STREAM):
            name = group["name"]
            await redis.xgroup_destroy(STREAM, name)
    await redis.delete(STREAM, "transactions:dlq")


async def current_group_lag(redis: Redis) -> int:
    groups = await redis.xinfo_groups(STREAM)
    for group in groups:
        if group["name"] == GROUP:
            lag = group.get("lag")
            if lag is None:
                raise RuntimeError("Redis Streams group lag is unavailable; use Redis 7")
            return int(lag)
    return 0


async def wait_for_workers(
    redis: Redis, processes: list[tuple[subprocess.Popen[bytes], Any]]
) -> None:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        for process, _log in processes:
            if process.poll() is not None:
                raise RuntimeError(f"worker exited during benchmark startup ({process.returncode})")
        try:
            if await current_group_lag(redis) >= 0:
                return
        except Exception:
            await asyncio.sleep(0.25)
    raise TimeoutError("worker group did not start")


async def wait_until_drained(redis: Redis, timeout: float = 180) -> int:
    peak_lag = 0
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        lag = await current_group_lag(redis)
        peak_lag = max(peak_lag, lag)
        summary = await redis.xpending(STREAM, GROUP)
        if lag == 0 and int(summary["pending"]) == 0:
            return peak_lag
        await asyncio.sleep(0.25)
    raise TimeoutError("worker did not drain the transaction stream")


async def query_results() -> tuple[int, float | None, float | None]:
    async with engine.connect() as connection:
        row = (
            await connection.execute(
                text(
                    "SELECT COUNT(*), "
                    "percentile_cont(0.50) WITHIN GROUP (ORDER BY "
                    "EXTRACT(EPOCH FROM (persisted_at - ingested_at)) * 1000), "
                    "percentile_cont(0.99) WITHIN GROUP (ORDER BY "
                    "EXTRACT(EPOCH FROM (persisted_at - ingested_at)) * 1000) "
                    "FROM transactions"
                )
            )
        ).one()
    return int(row[0]), row[1], row[2]


async def stop_workers(processes: list[tuple[subprocess.Popen[bytes], Any]]) -> None:
    for process, _log in processes:
        if process.poll() is None:
            process.send_signal(signal.SIGTERM)
    for process, log_file in processes:
        if process.poll() is None:
            try:
                await asyncio.to_thread(process.wait, 15)
            except subprocess.TimeoutExpired:
                process.kill()
                await asyncio.to_thread(process.wait)
        log_file.close()


def start_workers(
    count: int, batch_size: int, run_id: str
) -> list[tuple[subprocess.Popen[bytes], Any]]:
    processes: list[tuple[subprocess.Popen[bytes], Any]] = []
    log_dir = BACKEND_ROOT / "bench" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    for index in range(count):
        log_file = (log_dir / f"{run_id}-worker-{index + 1}.log").open("wb")
        env = os.environ.copy()
        env["WORKER_BATCH_SIZE"] = str(batch_size)
        process = subprocess.Popen(
            [sys.executable, "-m", "worker.main"],
            cwd=BACKEND_ROOT,
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )
        processes.append((process, log_file))
    return processes


async def run_case(
    redis: Redis,
    *,
    rate: int,
    duration: int,
    worker_count: int,
    batch_size: int,
    account_count: int,
    seed: int,
    api_url: str,
) -> dict[str, Any]:
    await clean_database_and_stream(redis)
    run_id = f"{rate}tps-{worker_count}workers-{uuid4().hex[:8]}"
    processes = start_workers(worker_count, batch_size, run_id)
    stop_sampler = asyncio.Event()
    sampler: asyncio.Task[None] | None = None
    peak_lag = 0

    async def sample_lag() -> None:
        nonlocal peak_lag
        while not stop_sampler.is_set():
            try:
                peak_lag = max(peak_lag, await current_group_lag(redis))
            except Exception:
                logger.exception("benchmark.lag_sample_failed", rate=rate)
            await asyncio.sleep(0.5)

    try:
        await wait_for_workers(redis, processes)
        generator = TrafficGenerator(seed, account_count, rate, 0.02)
        bucket = AsyncTokenBucket(rate)
        http_latencies: list[float] = []
        accepted_count = 0
        sampler = asyncio.create_task(sample_lag())
        batch: list[SimulatedTransaction] = []
        accepted_started = time.monotonic()
        async with httpx.AsyncClient(timeout=30) as client:
            while time.monotonic() - accepted_started < duration:
                await bucket.acquire()
                batch.append(generator.generate())
                if len(batch) >= batch_size:
                    accepted_count += await send_batch(client, api_url, batch, http_latencies)
                    await _write_labels(batch)
                    batch.clear()
            if batch:
                accepted_count += await send_batch(client, api_url, batch, http_latencies)
                await _write_labels(batch)

        peak_lag = max(peak_lag, await wait_until_drained(redis))
        row_count, e2e_p50, e2e_p99 = await query_results()
        dlq_count = await redis.xlen("transactions:dlq")
        return {
            "rate": rate,
            "workers": worker_count,
            "accepted_tps": accepted_count / duration,
            "http_p50": percentile(http_latencies, 0.50),
            "http_p99": percentile(http_latencies, 0.99),
            "e2e_p50": e2e_p50,
            "e2e_p99": e2e_p99,
            "peak_lag": peak_lag,
            "dlq": dlq_count,
            "rows": row_count,
            "run_id": run_id,
        }
    finally:
        stop_sampler.set()
        if sampler is not None:
            await sampler
        await stop_workers(processes)


async def send_batch(
    client: httpx.AsyncClient,
    api_url: str,
    batch: list[SimulatedTransaction],
    latencies: list[float],
) -> int:
    payload = [item.transaction.model_dump(mode="json") for item in batch]
    started = time.perf_counter()
    response = await client.post(f"{api_url.rstrip('/')}/ingest/transactions", json=payload)
    latencies.append((time.perf_counter() - started) * 1000)
    response.raise_for_status()
    return int(response.json()["accepted_count"])


def format_ms(value: Any) -> str:
    return "N/A" if value is None else f"{float(value):.2f}"


def write_results(machine: str, rows: list[dict[str, Any]], batch_size: int) -> None:
    lines = [
        "# Ingest Benchmark Results",
        "",
        f"Run date: {datetime.now(UTC).isoformat()}",
        f"Machine: {machine}",
        f"Worker batch size: {batch_size}",
        "HTTP latency is per batch request; end-to-end latency is transaction-level ",
        "`persisted_at - ingested_at` in milliseconds.",
        "",
        (
            "| Target tx/s | Workers | Accepted tx/s | HTTP p50 ms | HTTP p99 ms | "
            "E2E p50 ms | E2E p99 ms | Peak stream lag | DLQ | DB rows |"
        ),
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['rate']} | {row['workers']} | {row['accepted_tps']:.2f} | "
            f"{format_ms(row['http_p50'])} | {format_ms(row['http_p99'])} | "
            f"{format_ms(row['e2e_p50'])} | {format_ms(row['e2e_p99'])} | "
            f"{row['peak_lag']} | {row['dlq']} | {row['rows']} |"
        )
    lines.extend(
        [
            "",
            "The runner requires `--confirm-clean`; each case truncates pipeline data tables and",
            "deletes the transaction/DLQ streams before starting its worker process(es).",
            "",
        ]
    )
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text("\n".join(lines), encoding="utf-8")


async def main_async(args: argparse.Namespace) -> None:
    database = get_settings().database_url
    if not args.confirm_clean:
        raise SystemExit("Refusing destructive benchmark without --confirm-clean")
    if "underlock" not in database.rsplit("/", 1)[-1]:
        raise SystemExit("Refusing to truncate a database whose name does not contain 'underlock'")

    settings = get_settings()
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    rows: list[dict[str, Any]] = []
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            health = await client.get(f"{args.api_url.rstrip('/')}/health")
            health.raise_for_status()
        machine = machine_description()
        for rate in args.rates:
            result = await run_case(
                redis,
                rate=rate,
                duration=args.duration,
                worker_count=args.workers,
                batch_size=args.batch_size,
                account_count=args.accounts,
                seed=args.seed,
                api_url=args.api_url,
            )
            rows.append(result)
            write_results(machine, rows, args.batch_size)
            logger.info("benchmark.case_complete", **result)

        highest_rate = max(args.rates)
        for worker_count in args.scaling_workers:
            if worker_count == args.workers:
                continue
            result = await run_case(
                redis,
                rate=highest_rate,
                duration=args.duration,
                worker_count=worker_count,
                batch_size=args.batch_size,
                account_count=args.accounts,
                seed=args.seed,
                api_url=args.api_url,
            )
            rows.append(result)
            write_results(machine, rows, args.batch_size)
            logger.info("benchmark.case_complete", **result)
    finally:
        await redis.aclose()
        await engine.dispose()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rates", nargs="+", type=int, default=[100, 500, 1000, 2000])
    parser.add_argument("--duration", type=int, default=60)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--scaling-workers", nargs="+", type=int, default=[1, 2, 4])
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--accounts", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=123)
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("--confirm-clean", action="store_true")
    args = parser.parse_args()
    if args.duration <= 0 or args.batch_size < 1 or args.accounts < 4:
        parser.error("duration and batch size must be positive; accounts must be at least 4")
    if any(rate <= 0 for rate in args.rates + args.scaling_workers):
        parser.error("rates and worker counts must be positive")
    return args


if __name__ == "__main__":
    asyncio.run(main_async(parse_args()))