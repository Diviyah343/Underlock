import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select

from api.database import SessionFactory
from api.models import Account, Alert, Analyst, AuditLog, Case, CaseAlert, Rule, Settings, Transaction

RULES = (
    {
        "key": "amount-average",
        "title": "Flag transactions over 10x account average",
        "description": (
            "Triggers when an outflow exceeds the 90-day moving average volume by 10x or greater."
        ),
        "enabled": True,
        "params": {"multiplier": 10, "window_days": 90},
    },
    {
        "key": "new-beneficiary-high-amount",
        "title": "Flag new beneficiary + high amount within 1 hour",
        "description": (
            "Triggers on wires exceeding $25,000 sent within 60 minutes of counterparty creation."
        ),
        "enabled": True,
        "params": {"minimum_amount": 25000, "window_minutes": 60},
    },
    {
        "key": "new-device-transfer",
        "title": "Flag login from new device + immediate transfer",
        "description": (
            "Evaluates session fingerprint mismatch followed by transaction dispatch "
            "within 5 minutes."
        ),
        "enabled": True,
        "params": {"window_minutes": 5},
    },
    {
        "key": "multi-hop-transfer",
        "title": "Flag multi-hop rapid fund transfers",
        "description": (
            "Identifies accounts receiving and forwarding equal sums across 3 or more nodes "
            "within 24 hours."
        ),
        "enabled": False,
        "params": {"minimum_nodes": 3, "window_hours": 24},
    },
)

CASE_TITLES = (
    "Velocity spike on Antwerp outbound wire",
    "Beneficiary mismatch against KYC refresh",
    "New device paired with rapid disbursement",
)

ALERT_TIERS = ("high", "med", "low")
PRIORITIES = ("P1-AML", "P2-FRAUD", "P3-KYC")
ACTIONS = (
    "HOLD_DISBURSEMENT",
    "BLOCK_ACCOUNT",
    "REQUEST_KYC_REVIEW",
    "ESCALATE_TO_ANALYST",
)


def risk_factors_for(index: int) -> list[dict[str, object]]:
    templates = [
        {
            "title": "Geographic velocity anomaly",
            "weight_pct": 38,
            "description": "Session initiated from a new location and crossed the expected velocity threshold in under 20 minutes.",
        },
        {
            "title": "Device fingerprint divergence",
            "weight_pct": 27,
            "description": "The device signature differs from the account's common browser and TLS fingerprint stack.",
        },
        {
            "title": "Beneficiary mismatch",
            "weight_pct": 22,
            "description": "First-time beneficiary creation immediately precedes a near-threshold transfer without escalation.",
        },
        {
            "title": "Amount deviation",
            "weight_pct": 13,
            "description": "The amount is above the account's 90-day median and exceeds analyst review thresholds.",
        },
    ]
    return [
        {**factor, "weight_pct": factor["weight_pct"] + ((index + 1) % 3) * 2}
        for factor in templates
    ]


async def seed() -> None:
    async with SessionFactory.begin() as session:
        analyst_ids: dict[str, Analyst] = {}
        for analyst_data in (
            ("AN-8902", "Eleni Vance", "Senior Analyst", "eleni.vance@example.com"),
            ("AN-7711", "Maya Shankar", "AML Specialist", "maya.shankar@example.com"),
            ("AN-6628", "Jonas Nair", "Fraud Operations", "jonas.nair@example.com"),
        ):
            analyst_code, name, role, email = analyst_data
            analyst = await session.scalar(
                select(Analyst).where(Analyst.analyst_code == analyst_code)
            )
            if analyst is None:
                analyst = Analyst(
                    name=name,
                    analyst_code=analyst_code,
                    role=role,
                    email=email,
                )
                session.add(analyst)
                await session.flush()
            analyst_ids[analyst_code] = analyst

        rule_map: dict[str, Rule] = {}
        for rule_data in RULES:
            rule = await session.scalar(select(Rule).where(Rule.key == rule_data["key"]))
            if rule is None:
                rule = Rule(**rule_data)
                session.add(rule)
                await session.flush()
            rule_map[rule_data["key"]] = rule

        if await session.get(Settings, 1) is None:
            session.add(Settings(id=1, threshold_medium=40, threshold_high=75))

        account_defs = (
            ("ACCT-1001", "Northwind Holdings", "US", "KYC-1001", Decimal("12500.00"), 82),
            ("ACCT-1002", "Crescent Logistics", "GB", "KYC-1002", Decimal("8400.00"), 61),
            ("ACCT-1003", "Blue Harbor Retail", "SG", "KYC-1003", None, 43),
            ("ACCT-1004", "Harborline Energy", "US", "KYC-1004", Decimal("15000.00"), 74),
        )
        accounts: list[Account] = []
        for external_ref, name, jurisdiction, kyc_ref, avg_outflow, risk_index in account_defs:
            account = await session.scalar(select(Account).where(Account.external_ref == external_ref))
            if account is None:
                account = Account(
                    external_ref=external_ref,
                    name=name,
                    jurisdiction=jurisdiction,
                    kyc_ref=kyc_ref,
                    avg_90d_outflow=avg_outflow,
                    risk_index=risk_index,
                )
                session.add(account)
                await session.flush()
            accounts.append(account)

        case_rows: list[Case] = []
        for index, title in enumerate(CASE_TITLES, start=1):
            case_code = f"CASE-{2025000 + index}"
            case = await session.scalar(select(Case).where(Case.case_code == case_code))
            if case is None:
                case = Case(
                    case_code=case_code,
                    title=title,
                    status=["open", "under_review", "closed"][index % 3],
                    assignee=next(iter(analyst_ids.values())).id,
                    created_at=datetime.now(UTC) - timedelta(days=index * 2),
                    closed_at=(datetime.now(UTC) - timedelta(days=index)) if index == 3 else None,
                    last_activity_at=datetime.now(UTC) - timedelta(hours=index * 4),
                )
                session.add(case)
                await session.flush()
            case_rows.append(case)

        transaction_rows: list[Transaction] = []
        for index in range(24):
            account = accounts[index % len(accounts)]
            tx_hash = f"seed-{index:03d}-{uuid4().hex[:8]}"
            tx = Transaction(
                idempotency_key=f"seed-idem-{index:03d}-{uuid4().hex[:8]}",
                tx_hash=tx_hash,
                account_id=account.id,
                amount=Decimal(str(850 + (index * 137.5))),
                currency="USD",
                jurisdiction=account.jurisdiction,
                ip_address=f"203.0.113.{(index % 20) + 10}",
                ip=f"203.0.113.{(index % 20) + 10}",
                location_country=["US", "GB", "SG", "BE"][index % 4],
                device_signature=f"dev-sig-{index:02d}",
                origin_channel=["web", "mobile", "branch", "api"][index % 4],
                beneficiary_entity=f"Beneficiary {index + 1}",
                beneficiary_bank=["CITI", "HSBC", "ING", "DB"][index % 4],
                direction="outflow" if index % 2 == 0 else "inflow",
                tx_type=["TRANSFER", "PAYMENT", "CASH_OUT"][index % 3],
                occurred_at=datetime.now(UTC) - timedelta(hours=index * 2),
                status=["flagged", "review", "cleared"][index % 3],
                model_version="hydra-v4.2",
                risk_score=35 + index,
            )
            session.add(tx)
            transaction_rows.append(tx)
        await session.flush()

        alert_count = 0
        for index in range(20):
            tx = transaction_rows[index]
            case = case_rows[index % len(case_rows)]
            rule = next(iter(rule_map.values()))
            if index % 4 == 0:
                rule = rule_map["new-device-transfer"]
            elif index % 4 == 1:
                rule = rule_map["new-beneficiary-high-amount"]
            elif index % 4 == 2:
                rule = rule_map["amount-average"]

            opened = datetime.now(UTC) - timedelta(hours=index * 2, minutes=index * 7)
            alert = Alert(
                transaction_id=tx.id,
                source="rule",
                rule_key=rule.key,
                rule_id=rule.id,
                severity=["low", "medium", "high"][index % 3],
                tier=ALERT_TIERS[index % 3],
                priority=PRIORITIES[index % 3],
                opened_at=opened,
                sla_deadline=opened + timedelta(hours=6),
                model_version="hydra-v4.2",
                automation_action=ACTIONS[index % len(ACTIONS)],
                incident_ref=f"INC-{20250000 + index}",
                risk_score=42 + (index * 3),
                status=["open", "acknowledged", "dismissed"][index % 3],
                risk_factors=risk_factors_for(index),
                explanation={
                    "summary": f"Pattern matched rule {rule.key} for suspicious transaction activity.",
                    "confidence": 0.82 + (index % 5) * 0.03,
                },
                case_id=case.id,
            )
            session.add(alert)
            await session.flush()
            alert_count += 1

            session.add(
                CaseAlert(
                    case_id=case.id,
                    alert_id=alert.id,
                )
            )

            analyst = next(iter(analyst_ids.values()))
            session.add(
                AuditLog(
                    actor_id=analyst.id,
                    action="alert_seeded",
                    entity_type="alert",
                    entity_id=alert.id,
                    details={
                        "rule_key": rule.key,
                        "priority": alert.priority,
                        "status": alert.status,
                    },
                )
            )

        if alert_count < 20:
            raise RuntimeError(f"Seeded only {alert_count} alerts; expected at least 20")


if __name__ == "__main__":
    asyncio.run(seed())
