.PHONY: up down run run-scoring run-worker simulate test test-integration benchmark preflight lint migrate seed openapi

up:
	docker compose up -d --wait

down:
	docker compose down

run:
	uv run uvicorn api.main:app --reload

run-scoring:
	uv run uvicorn scoring.main:app --reload --port 8001

run-worker:
	uv run python -m worker.main

simulate:
	uv run python -m simulator $(ARGS)

test:
	uv run pytest

test-integration:
	docker compose up -d --wait
	uv run alembic upgrade head
	uv run python -m api.seed
	uv run pytest -m integration -q

benchmark:
	uv run python scripts/bench_ingest.py --confirm-clean

preflight:
	uv run python scripts/preflight.py

lint:
	uv run ruff check api shared worker scoring simulator scripts
	uv run mypy api shared worker scoring simulator scripts

migrate:
	uv run alembic upgrade head

seed:
	uv run python -m api.seed

openapi:
	uv run python scripts/export_openapi.py