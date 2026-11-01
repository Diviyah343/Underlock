# Ingest Benchmark Results

## Environment

- Host: Windows 11 workspace; Intel Core i5-1335U, 10 cores / 12 threads; 7.6 GiB RAM.
- Docker: Docker CLI is unavailable, so Docker/WSL2/VM configuration could not be verified.
- Local Redis listener: reports Redis-compatible version 3.0.504; `XADD` and `XGROUP` return `unknown command`.
- Local PostgreSQL listener: accepts TCP but rejects the configured `underlock` password. No backend `.env` or `DATABASE_URL` override is present.
- Worker processes: not started successfully against the available Redis service. Batch size: 100 (configured default).

## Results

Live benchmark runs were blocked by the infrastructure mismatch above. No rates or latencies are inferred.

| Target tx/s | Workers | Accepted tx/s | HTTP p50 ms | HTTP p99 ms | E2E p50 ms | E2E p99 ms | Peak stream lag | DLQ |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | 1 | Not run | Not run | Not run | Not run | Not run | Not run | Not run |
| 500 | 1 | Not run | Not run | Not run | Not run | Not run | Not run | Not run |
| 1000 | 1 | Not run | Not run | Not run | Not run | Not run | Not run | Not run |
| 2000 | 1 | Not run | Not run | Not run | Not run | Not run | Not run | Not run |
| 2000 | 2 | Not run | Not run | Not run | Not run | Not run | Not run | Not run |
| 2000 | 4 | Not run | Not run | Not run | Not run | Not run | Not run | Not run |

The 500 tx/s end-to-end p99 threshold could not be evaluated, so no profiling or performance fix was claimed.