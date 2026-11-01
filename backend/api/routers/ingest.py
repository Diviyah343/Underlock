import json
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Body, Header, HTTPException, Request, Response, status
from pydantic import Field
from redis.exceptions import RedisError

from shared.schemas import (
    IngestItemResult,
    IngestResponse,
    IngestTransaction,
    TransactionIngestPayload,
)

router = APIRouter(prefix="/ingest", tags=["ingestion"])
BatchIngest = Annotated[list[IngestTransaction], Field(min_length=1, max_length=500)]
IngestBody = Annotated[TransactionIngestPayload | BatchIngest, Body()]

ENQUEUE_SCRIPT = """
local results = {}
for i = 1, #ARGV, 3 do
    local idempotency_key = 'idem:' .. ARGV[i]
    local original_status = redis.call('GET', idempotency_key)
    if original_status then
        table.insert(results, original_status)
        table.insert(results, '1')
    else
        local claimed = redis.call('SET', idempotency_key, 'accepted', 'NX', 'EX', 86400)
        if claimed then
            local result = redis.pcall(
                'XADD', KEYS[1], 'MAXLEN', '~', 1000000, '*',
                'payload', ARGV[i + 1], 'ingested_at', ARGV[i + 2]
            )
            if type(result) == 'table' and result.err then
                redis.call('DEL', idempotency_key)
                return redis.error_reply(result.err)
            end
            table.insert(results, 'accepted')
            table.insert(results, '0')
        else
            table.insert(results, redis.call('GET', idempotency_key) or 'accepted')
            table.insert(results, '1')
        end
    end
end
return results
"""


@router.post(
    "/transactions",
    response_model=IngestResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        200: {"model": IngestResponse, "description": "Idempotent duplicate"},
        503: {
            "description": "Redis queue unavailable",
            "headers": {"Retry-After": {"schema": {"type": "string"}}},
        },
    },
)
async def ingest_transaction(
    payload: IngestBody,
    request: Request,
    response: Response,
    idempotency_key: Annotated[
        str | None, Header(alias="Idempotency-Key", min_length=1, max_length=255)
    ] = None,
) -> IngestResponse:
    if isinstance(payload, list):
        keys = [item.idempotency_key for item in payload]
        payloads = [item.model_dump(mode="json") for item in payload]
    else:
        if idempotency_key is None or not idempotency_key.strip():
            raise HTTPException(
                status_code=422, detail="Idempotency-Key is required for a single post"
            )
        keys = [idempotency_key.strip()]
        payloads = [payload.model_dump(mode="json")]

    ingested_at = datetime.now(UTC).isoformat()
    script_args: list[str] = []
    for key, item in zip(keys, payloads, strict=True):
        item["idempotency_key"] = key
        script_args.extend((key, json.dumps(item, separators=(",", ":")), ingested_at))

    redis: Any = request.app.state.redis
    try:
        statuses: list[str] = await redis.eval(ENQUEUE_SCRIPT, 1, "transactions", *script_args)
    except (RedisError, TimeoutError) as exc:
        raise HTTPException(
            status_code=503,
            detail="Transaction queue is unavailable; retry this request",
            headers={"Retry-After": "1"},
        ) from exc

    items = [
        IngestItemResult(
            idempotency_key=key,
            status=statuses[index * 2],
            duplicate=statuses[index * 2 + 1] == "1",
        )
        for index, key in enumerate(keys)
    ]
    duplicate_count = sum(item.duplicate for item in items)
    accepted_count = len(items) - duplicate_count
    response.status_code = 200 if accepted_count == 0 else 202
    return IngestResponse(
        accepted_count=accepted_count,
        duplicate_count=duplicate_count,
        items=items,
    )
