# Underlock backend

Python monorepo for the API, Redis Streams worker, traffic simulator, and scoring placeholder.
The API uses FastAPI, Pydantic v2, async SQLAlchemy, Alembic, and PostgreSQL.

## Local development

Requirements: Python 3.11+, [uv](https://docs.astral.sh/uv/), Node.js/npm for TypeScript generation.

```sh
cd backend
uv sync --dev
cp .env.example .env
# Set JWT_SECRET_KEY (at least 32 characters) and SIMULATOR_ANALYST_PASSWORD
# (at least 12 characters) in .env before starting services.
docker compose up -d --build
```

The full Compose stack runs PostgreSQL, Redis, migrations, seed data, analyst
password provisioning, the API, the worker, and a continuous simulator. The
simulator defaults to 5 transactions/second and a 10% fraud-injection rate;
override these with `SIMULATOR_RATE` and `SIMULATOR_FRAUD_RATE` in `.env`.
The browser API is available at `http://localhost:8000`, and
`API_CORS_ORIGINS` controls allowed browser origins (including the Vite default
`http://localhost:5173`).

For host-based development instead of the full Compose stack, start only the
database dependencies, then run the migration, seed, API, worker, and simulator
commands below:

```sh
docker compose up -d postgres redis
make migrate
make seed
make run
```

## Windows setup

Install Docker Desktop, enable the WSL 2 backend, and start Docker Desktop before
running Compose. If WSL is competing with other workloads on a 8 GiB machine, an
optional `%UserProfile%\.wslconfig` memory cap is:

```ini
[wsl2]
memory=4GB
processors=4
swap=2GB
```

After changing `.wslconfig`, run `wsl --shutdown` and restart Docker Desktop. The
Compose host ports avoid the unrelated local services: PostgreSQL is at
`localhost:5433` and Redis 7 is at `localhost:6380`; their container ports stay
5432 and 6379. Generate the ignored local config once with
`Copy-Item .env.example .env`.

There is no GNU Make requirement on Windows. For host-based development, start
only PostgreSQL and Redis with `docker compose up -d postgres redis`. From
`/backend`, use the PowerShell task runner; each long-lived process command
should be opened in its own terminal:

```powershell
docker compose up -d postgres redis
.\scripts\tasks.ps1 preflight
.\scripts\tasks.ps1 migrate
.\scripts\tasks.ps1 seed
```

Open separate terminals for the API, worker, and simulator:

```powershell
.\scripts\tasks.ps1 api
.\scripts\tasks.ps1 worker
.\scripts\tasks.ps1 sim --duration 30 --seed 123
```

Other PowerShell equivalents are `test`, `test-integration`, `bench`, `lint`,
`scoring`, `openapi`, and `down`. The GNU Make equivalents include `make up`,
`make preflight`, `make run`, `make run-worker`, `make simulate ARGS="--duration 30"`,
`make test`, `make test-integration`, `make benchmark`, `make lint`, `make migrate`,
`make seed`, `make openapi`, `make run-scoring`, and `make down`.

`scripts/preflight.py` checks Redis version and Streams, PostgreSQL connectivity,
the Alembic head revision, and presence of all four seed rules. It reports a repair
command for each failed check. The API and worker run the same Redis check before
starting.

The API listens at `http://localhost:8000`; interactive OpenAPI docs are at
`http://localhost:8000/docs`. The scoring placeholder listens at port 8001 with
`make run-scoring`.

Run the Redis Streams consumer in another terminal with `make run-worker`. Generate
traffic with `make simulate ARGS="--duration 30"`; omit duration or set it to `0`
to run continuously. Each run chooses a fresh seed by default so restarts do not
replay idempotency keys; pass `--seed 123` for reproducible traffic. The simulator
retries queue outages and writes ground-truth rows directly to `sim_labels`, never
in transaction requests.

Set `JWT_SECRET_KEY` in `.env` to a generated secret of at least 32 characters before
using analyst authentication (generate one with
`uv run python -c "import secrets; print(secrets.token_urlsafe(48))"`). Provision an
analyst password interactively with
`uv run python scripts/provision_analyst_password.py`; the password is stored only as
an Argon2 hash. Analysts without a provisioned password cannot log in. Use
`POST /auth/login` with `analyst_code` and `password`, then send the returned bearer
token to protected API routes. `POST /auth/logout` revokes that token until it expires.
Login, logout, and analyst alert decisions are written to `audit_log`.

Use `make test` and `make lint` for checks. `make openapi` writes `openapi.json` in
this directory and invokes `npx openapi-typescript` to write
`../frontend/src/api/types.ts`. Type generation requires that frontend path to exist
or be creatable in the consuming repository.

`POST /ingest/transactions` accepts one transaction with an `Idempotency-Key` header
or a list of up to 500 items with per-item keys. It atomically reserves keys in Redis
and appends new transactions to the `transactions` stream. The worker persists batches
to PostgreSQL and publishes compact events to `tx:events`; messages that fail five
times are moved to `transactions:dlq`.

The simulator's transaction keys and account/device/beneficiary identities are stable
for a given seed. Fraud labels are written directly to `sim_labels`, separate from the
API payload and transaction table. Other API routers and the scoring/worker ML behavior
remain outside this implementation step.