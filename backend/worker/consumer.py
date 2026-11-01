"""At-least-once Redis Streams persistence worker."""

import asyncio
import json
import time
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import structlog
from redis.asyncio import Redis
from redis.exceptions import RedisError, ResponseError
from sqlalchemy import case, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.config import AppSettings
from api.models import Account, AccountLink, Alert, Beneficiary, Device, Transaction
from shared.constants import ALERT_EVENT_CHANNEL, TRANSACTION_EVENT_CHANNEL
from shared.schemas import IngestTransaction

logger = structlog.get_logger()
STREAM = "transactions"
GROUP = "workers"
DLQ_STREAM = "transactions:dlq"
EVENT_CHANNEL = TRANSACTION_EVENT_CHANNEL

StreamEntry = tuple[str, dict[str, str]]
DecodedEntry = tuple[str, dict[str, str], IngestTransaction, datetime]


class TransactionConsumer:
    def __init__(
        self,
        redis: Redis,
        session_factory: async_sessionmaker[AsyncSession],
        consumer_name: str,
        settings: AppSettings,
    ) -> None:
        self.redis = redis
        self.session_factory = session_factory
        self.consumer_name = consumer_name
        self.settings = settings
        self.reclaim_cursor = "0-0"

    async def run(self, stop_event: asyncio.Event) -> None:
        try:
            await self.redis.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

        logger.info("worker.started", consumer=self.consumer_name, stream=STREAM, group=GROUP)
        await self.reclaim_pending()
        next_recovery = time.monotonic() + self.settings.worker_recovery_interval_ms / 1000

        while not stop_event.is_set():
            if time.monotonic() >= next_recovery:
                await self.reclaim_pending()
                next_recovery = time.monotonic() + self.settings.worker_recovery_interval_ms / 1000

            try:
                response = await self.redis.xreadgroup(
                    GROUP,
                    self.consumer_name,
                    {STREAM: ">"},
                    count=self.settings.worker_batch_size,
                    block=self.settings.worker_block_ms,
                )
            except RedisError:
                logger.exception("worker.redis_read_failed")
                await asyncio.sleep(1)
                continue

            entries = self._flatten(response)
            if entries:
                try:
                    await self.process_entries(entries)
                except RedisError:
                    logger.exception("worker.redis_process_failed", batch_size=len(entries))

        logger.info("worker.stopped", consumer=self.consumer_name)

    async def reclaim_pending(self) -> None:
        while True:
            try:
                next_cursor, messages, _deleted = await self.redis.xautoclaim(
                    STREAM,
                    GROUP,
                    self.consumer_name,
                    min_idle_time=self.settings.worker_min_idle_ms,
                    start_id=self.reclaim_cursor,
                    count=self.settings.worker_batch_size,
                )
            except RedisError:
                logger.exception("worker.autoclaim_failed")
                return

            entries = self._flatten([(STREAM, messages)])
            if entries:
                try:
                    await self.process_entries(entries)
                except RedisError:
                    logger.exception(
                        "worker.redis_recovery_process_failed", batch_size=len(entries)
                    )
            self.reclaim_cursor = str(next_cursor)
            if self.reclaim_cursor == "0-0":
                break

    @staticmethod
    def _flatten(response: Any) -> list[StreamEntry]:
        flattened: list[StreamEntry] = []
        for _stream_name, entries in response or []:
            flattened.extend((str(message_id), fields) for message_id, fields in entries)
        return flattened

    async def _delivery_counts(self, message_ids: Sequence[str]) -> dict[str, int]:
        pipeline = self.redis.pipeline(transaction=False)
        for message_id in message_ids:
            pipeline.xpending_range(STREAM, GROUP, message_id, message_id, 1)
        responses = await pipeline.execute()
        counts: dict[str, int] = {}
        for message_id, pending_entries in zip(message_ids, responses, strict=True):
            if pending_entries:
                counts[message_id] = int(pending_entries[0]["times_delivered"])
        return counts

    async def process_entries(self, entries: Sequence[StreamEntry]) -> None:
        attempts = await self._delivery_counts([message_id for message_id, _ in entries])
        valid: list[DecodedEntry] = []
        invalid: list[tuple[str, dict[str, str], str]] = []

        for message_id, fields in entries:
            try:
                payload = IngestTransaction.model_validate(json.loads(fields["payload"]))
                ingested_at = datetime.fromisoformat(fields["ingested_at"])
                if ingested_at.tzinfo is None:
                    raise ValueError("ingested_at must be timezone-aware")
                valid.append((message_id, fields, payload, ingested_at))
            except (KeyError, TypeError, ValueError) as exc:
                invalid.append((message_id, fields, str(exc)))

        ack_ids: list[str] = []
        for message_id, fields, error in invalid:
            delivery_count = attempts.get(message_id, 0)
            if delivery_count >= self.settings.worker_max_deliveries:
                await self._dead_letter(message_id, fields, error, delivery_count)
                ack_ids.append(message_id)

        if valid:
            batch_started = time.monotonic()
            try:
                batch_events, inserted_count = await self.persist_batch(valid)
            except Exception as exc:
                logger.exception(
                    "worker.batch_persist_failed",
                    batch_size=len(valid),
                    error=str(exc),
                )
                for message_id, fields, _payload, _ingested_at in valid:
                    delivery_count = attempts.get(message_id, 0)
                    if delivery_count >= self.settings.worker_max_deliveries:
                        await self._dead_letter(message_id, fields, str(exc), delivery_count)
                        ack_ids.append(message_id)
            else:
                for event in batch_events:
                    await self.redis.publish(
                        EVENT_CHANNEL, json.dumps(event, separators=(",", ":"))
                    )
                    alert_event = event.get("alert")
                    if alert_event is not None:
                        await self.redis.publish(
                            ALERT_EVENT_CHANNEL,
                            json.dumps(alert_event, separators=(",", ":")),
                        )
                ack_ids.extend(message_id for message_id, _fields, _payload, _at in valid)
                oldest = min(item[3] for item in valid)
                logger.info(
                    "worker.batch_persisted",
                    batch_size=len(valid),
                    inserted=inserted_count,
                    db_time_ms=round((time.monotonic() - batch_started) * 1000, 2),
                    lag_ms=max(0, round((datetime.now(UTC) - oldest).total_seconds() * 1000)),
                )

        if ack_ids:
            await self.redis.xack(STREAM, GROUP, *ack_ids)

    async def _dead_letter(
        self, message_id: str, fields: dict[str, str], error: str, attempts: int
    ) -> None:
        await self.redis.xadd(
            DLQ_STREAM,
            {
                "source_id": message_id,
                "payload": fields.get("payload", ""),
                "ingested_at": fields.get("ingested_at", ""),
                "error": error[:2000],
                "attempts": str(attempts),
                "failed_at": datetime.now(UTC).isoformat(),
            },
        )
        logger.error("worker.message_dead_lettered", message_id=message_id, attempts=attempts)

    async def persist_batch(
        self, entries: Sequence[DecodedEntry]
    ) -> tuple[list[dict[str, str]], int]:
        persisted_at = datetime.now(UTC)
        account_rows: dict[UUID, dict[str, Any]] = {}
        device_rows: dict[UUID, dict[str, Any]] = {}
        beneficiary_rows: dict[UUID, dict[str, Any]] = {}
        transaction_rows: list[dict[str, Any]] = []
        payload_by_key: dict[str, IngestTransaction] = {}

        for _message_id, _fields, payload, ingested_at in entries:
            payload_by_key[payload.idempotency_key] = payload
            account_rows[payload.account_id] = {
                "id": payload.account_id,
                "external_ref": payload.account_external_ref or str(payload.account_id),
                "jurisdiction": payload.jurisdiction,
                "avg_90d_outflow": payload.avg_90d_outflow,
            }
            if payload.counterparty_account_id is not None:
                account_rows.setdefault(
                    payload.counterparty_account_id,
                    {
                        "id": payload.counterparty_account_id,
                        "external_ref": payload.counterparty_external_ref
                        or str(payload.counterparty_account_id),
                        "jurisdiction": payload.counterparty_jurisdiction or payload.jurisdiction,
                        "avg_90d_outflow": None,
                    },
                )
            if payload.device_id is not None:
                device_rows[payload.device_id] = {
                    "id": payload.device_id,
                    "fingerprint": payload.device_fingerprint or str(payload.device_id),
                    "first_seen_at": payload.device_first_seen_at or payload.occurred_at,
                }
            if payload.beneficiary_id is not None:
                beneficiary_rows[payload.beneficiary_id] = {
                    "id": payload.beneficiary_id,
                    "account_id": payload.account_id,
                    "counterparty_ref": payload.beneficiary_ref or str(payload.beneficiary_id),
                    "created_at": payload.beneficiary_created_at or payload.occurred_at,
                }
            transaction_rows.append(
                {
                    "idempotency_key": payload.idempotency_key,
                    "tx_hash": payload.tx_hash,
                    "account_id": payload.account_id,
                    "counterparty_account_id": payload.counterparty_account_id,
                    "beneficiary_id": payload.beneficiary_id,
                    "amount": payload.amount,
                    "currency": payload.currency,
                    "jurisdiction": payload.jurisdiction,
                    "ip_address": payload.ip_address,
                    "device_id": payload.device_id,
                    "direction": payload.direction.value,
                    "tx_type": payload.tx_type.value,
                    "oldbalance_org": payload.oldbalance_org,
                    "newbalance_org": payload.newbalance_org,
                    "oldbalance_dest": payload.oldbalance_dest,
                    "newbalance_dest": payload.newbalance_dest,
                    "occurred_at": payload.occurred_at,
                    "ingested_at": ingested_at,
                    "persisted_at": persisted_at,
                }
            )

        async with self.session_factory() as session:
            async with session.begin():
                if account_rows:
                    account_insert = pg_insert(Account).values(list(account_rows.values()))
                    await session.execute(
                        account_insert.on_conflict_do_update(
                            index_elements=[Account.id],
                            set_={
                                "jurisdiction": account_insert.excluded.jurisdiction,
                                "avg_90d_outflow": func.coalesce(
                                    account_insert.excluded.avg_90d_outflow,
                                    Account.avg_90d_outflow,
                                ),
                            },
                        )
                    )
                if device_rows:
                    device_insert = pg_insert(Device).values(list(device_rows.values()))
                    await session.execute(
                        device_insert.on_conflict_do_update(
                            index_elements=[Device.id],
                            set_={
                                "first_seen_at": func.least(
                                    Device.first_seen_at, device_insert.excluded.first_seen_at
                                )
                            },
                        )
                    )
                if beneficiary_rows:
                    beneficiary_insert = pg_insert(Beneficiary).values(
                        list(beneficiary_rows.values())
                    )
                    await session.execute(
                        beneficiary_insert.on_conflict_do_update(
                            index_elements=[Beneficiary.id],
                            set_={
                                "account_id": beneficiary_insert.excluded.account_id,
                                "counterparty_ref": beneficiary_insert.excluded.counterparty_ref,
                                "created_at": func.least(
                                    Beneficiary.created_at, beneficiary_insert.excluded.created_at
                                ),
                            },
                        )
                    )

                insert_result = await session.execute(
                    pg_insert(Transaction)
                    .values(transaction_rows)
                    .on_conflict_do_nothing(index_elements=[Transaction.idempotency_key])
                    .returning(Transaction.idempotency_key, Transaction.id)
                )
                inserted = {
                    row._mapping["idempotency_key"]: row._mapping["id"] for row in insert_result
                }
                new_payloads = [payload_by_key[key] for key in inserted if key in payload_by_key]
                if new_payloads:
                    await self._upsert_account_links(session, new_payloads)
                event_result = await session.execute(
                    select(Transaction.idempotency_key, Transaction.id).where(
                        Transaction.idempotency_key.in_(payload_by_key)
                    )
                )
                event_ids = {
                    row._mapping["idempotency_key"]: row._mapping["id"] for row in event_result
                }

                alert_ids: dict[str, UUID] = {}
                for key, transaction_id in inserted.items():
                    payload = payload_by_key[key]
                    rule_key = self._alert_rule_for(payload)
                    if rule_key is None:
                        continue
                    alert = Alert(
                        transaction_id=transaction_id,
                        source="rule",
                        rule_key=rule_key,
                        severity="high",
                        tier="high",
                        priority="P1-AML",
                        opened_at=persisted_at,
                        sla_deadline=persisted_at + timedelta(hours=6),
                        automation_action="HOLD_DISBURSEMENT",
                        incident_ref=f"INC-{uuid4().hex[:20]}",
                        risk_score=90,
                        status="open",
                        risk_factors=[
                            {
                                "title": "Automated fraud rule match",
                                "weight_pct": 100,
                                "description": f"Transaction matched rule {rule_key}.",
                            }
                        ],
                        explanation={"rule_key": rule_key},
                    )
                    session.add(alert)
                    await session.flush()
                    alert_ids[key] = alert.id

            events = [
                {
                    "transaction_id": str(transaction_id),
                    "idempotency_key": key,
                    "account_id": str(payload_by_key[key].account_id),
                    "amount": str(payload_by_key[key].amount),
                    "currency": payload_by_key[key].currency,
                    "occurred_at": payload_by_key[key].occurred_at.isoformat(),
                    **(
                        {
                            "alert": {
                                "id": str(alert_ids[key]),
                                "transaction_id": str(transaction_id),
                                "account_id": str(payload_by_key[key].account_id),
                                "rule_key": self._alert_rule_for(payload_by_key[key]),
                                "risk_score": 90,
                                "status": "open",
                                "occurred_at": payload_by_key[key].occurred_at.isoformat(),
                            }
                        }
                        if key in alert_ids
                        else {}
                    ),
                }
                for key, transaction_id in event_ids.items()
            ]
            return events, len(inserted)

    @staticmethod
    def _alert_rule_for(payload: IngestTransaction) -> str | None:
        if (
            payload.direction.value == "outflow"
            and payload.avg_90d_outflow is not None
            and payload.avg_90d_outflow > 0
            and payload.amount >= payload.avg_90d_outflow * 10
        ):
            return "amount-average"
        if (
            payload.beneficiary_created_at is not None
            and payload.amount >= Decimal("25000")
            and timedelta(0)
            <= payload.occurred_at - payload.beneficiary_created_at
            <= timedelta(minutes=60)
        ):
            return "new-beneficiary-high-amount"
        if (
            payload.device_first_seen_at is not None
            and timedelta(0)
            <= payload.occurred_at - payload.device_first_seen_at
            <= timedelta(minutes=5)
        ):
            return "new-device-transfer"
        return None

    async def _upsert_account_links(
        self,
        session: AsyncSession,
        payloads: Sequence[IngestTransaction],
    ) -> None:
        link_rows: dict[tuple[UUID, UUID, str, str], dict[str, Any]] = {}

        def add_link(
            source_id: UUID,
            target_id: UUID,
            link_type: str,
            evidence: dict[str, str],
            observed_at: datetime,
            amount: Decimal | None = None,
        ) -> None:
            if source_id == target_id:
                return
            evidence_json = json.dumps(evidence, sort_keys=True, separators=(",", ":"))
            key = (source_id, target_id, link_type, evidence_json)
            row = {
                "source_account_id": source_id,
                "target_account_id": target_id,
                "type": link_type,
                "evidence": evidence,
                "amount": amount,
                "last_seen_at": observed_at,
            }
            current = link_rows.get(key)
            if current is None or observed_at >= current["last_seen_at"]:
                link_rows[key] = row

        for payload in payloads:
            if payload.direction.value == "outflow" and payload.counterparty_account_id:
                add_link(
                    payload.account_id,
                    payload.counterparty_account_id,
                    "fund_transfer",
                    {"currency": payload.currency},
                    payload.occurred_at,
                    payload.amount,
                )

        ips = {payload.ip_address for payload in payloads if payload.ip_address}
        devices = {payload.device_id for payload in payloads if payload.device_id}
        predicates = []
        if ips:
            predicates.append(Transaction.ip_address.in_(ips))
        if devices:
            predicates.append(Transaction.device_id.in_(devices))
        inserted_keys = {payload.idempotency_key for payload in payloads}
        peer_rows: list[tuple[UUID, str | None, UUID | None]] = []
        if predicates:
            result = await session.execute(
                select(
                    Transaction.account_id,
                    Transaction.ip_address,
                    Transaction.device_id,
                ).where(
                    or_(*predicates),
                    Transaction.idempotency_key.not_in(inserted_keys),
                )
            )
            peer_rows.extend((row[0], row[1], row[2]) for row in result.all())
        peer_rows.extend(
            (payload.account_id, payload.ip_address, payload.device_id) for payload in payloads
        )

        for payload in payloads:
            for peer_id, peer_ip, peer_device in peer_rows:
                if peer_id == payload.account_id:
                    continue
                if payload.ip_address and peer_ip == payload.ip_address:
                    evidence = {"ip_address": payload.ip_address}
                    add_link(
                        payload.account_id, peer_id, "shared_ip", evidence, payload.occurred_at
                    )
                    add_link(
                        peer_id, payload.account_id, "shared_ip", evidence, payload.occurred_at
                    )
                if payload.device_id and peer_device == payload.device_id:
                    evidence = {"device_id": str(payload.device_id)}
                    add_link(
                        payload.account_id,
                        peer_id,
                        "shared_device",
                        evidence,
                        payload.occurred_at,
                    )
                    add_link(
                        peer_id,
                        payload.account_id,
                        "shared_device",
                        evidence,
                        payload.occurred_at,
                    )

        if link_rows:
            excluded = pg_insert(AccountLink).excluded
            await session.execute(
                pg_insert(AccountLink)
                .values(list(link_rows.values()))
                .on_conflict_do_update(
                    index_elements=[
                        AccountLink.source_account_id,
                        AccountLink.target_account_id,
                        AccountLink.type,
                        AccountLink.evidence,
                    ],
                    set_={
                        "amount": case(
                            (excluded.last_seen_at >= AccountLink.last_seen_at, excluded.amount),
                            else_=AccountLink.amount,
                        ),
                        "last_seen_at": func.greatest(
                            AccountLink.last_seen_at, excluded.last_seen_at
                        ),
                    },
                )
            )
