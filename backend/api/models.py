from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

JSON_VALUE = JSON().with_variant(JSONB, "postgresql")


class Base(DeclarativeBase):
    pass


class Analyst(Base):
    __tablename__ = "analysts"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, server_default=func.gen_random_uuid())
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    analyst_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    role: Mapped[str] = mapped_column(String(80), nullable=False)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(256))


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (
        Index("ix_accounts_created_at", "created_at"),
        CheckConstraint("risk_index BETWEEN 0 AND 100", name="ck_accounts_risk_index"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, server_default=func.gen_random_uuid())
    external_ref: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    name: Mapped[str | None] = mapped_column(String(160))
    kyc_ref: Mapped[str | None] = mapped_column(String(80), index=True)
    jurisdiction: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    avg_90d_outflow: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    risk_index: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


class Beneficiary(Base):
    __tablename__ = "beneficiaries"
    __table_args__ = (Index("ix_beneficiaries_account_created", "account_id", "created_at"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, server_default=func.gen_random_uuid())
    account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id"), index=True)
    counterparty_ref: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, server_default=func.gen_random_uuid())
    fingerprint: Mapped[str] = mapped_column(String(256), unique=True, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint("direction IN ('inflow', 'outflow')", name="ck_transactions_direction"),
        CheckConstraint(
            "tx_type IN ('PAYMENT', 'TRANSFER', 'CASH_OUT', 'CASH_IN', 'DEBIT')",
            name="ck_transactions_tx_type",
        ),
        CheckConstraint(
            "status IN ('cleared', 'review', 'flagged')", name="ck_transactions_status"
        ),
        Index("ix_transactions_account_occurred", "account_id", "occurred_at"),
        Index("ix_transactions_counterparty_account", "counterparty_account_id"),
        Index("ix_transactions_beneficiary", "beneficiary_id"),
        Index("ix_transactions_device", "device_id"),
        Index(
            "ix_transactions_ip_activity_account",
            "ip_address",
            "occurred_at",
            "account_id",
        ),
        Index(
            "ix_transactions_device_activity_account",
            "device_id",
            "occurred_at",
            "account_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, server_default=func.gen_random_uuid())
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    tx_hash: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id"), nullable=False, index=True)
    counterparty_account_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("accounts.id"), index=True
    )
    beneficiary_id: Mapped[UUID | None] = mapped_column(ForeignKey("beneficiaries.id"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), index=True)
    ip: Mapped[str | None] = mapped_column(String(45), index=True)
    location_country: Mapped[str | None] = mapped_column(String(64), index=True)
    device_id: Mapped[UUID | None] = mapped_column(ForeignKey("devices.id"), index=True)
    device_signature: Mapped[str | None] = mapped_column(String(256))
    origin_channel: Mapped[str | None] = mapped_column(String(40), index=True)
    beneficiary_entity: Mapped[str | None] = mapped_column(String(160), index=True)
    beneficiary_bank: Mapped[str | None] = mapped_column(String(160), index=True)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    tx_type: Mapped[str] = mapped_column(String(16), nullable=False, server_default="PAYMENT")
    oldbalance_org: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    newbalance_org: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    oldbalance_dest: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    newbalance_dest: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
    persisted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    risk_score: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="cleared", index=True
    )
    model_version: Mapped[str | None] = mapped_column(String(64))


class Case(Base):
    __tablename__ = "cases"
    __table_args__ = (
        CheckConstraint("status IN ('open', 'under_review', 'closed')", name="ck_cases_status"),
        Index("ix_cases_status_activity", "status", "last_activity_at"),
        Index(
            "ix_cases_assigned_status_activity",
            "assigned_analyst_id",
            "status",
            "last_activity_at",
        ),
        Index(
            "ix_cases_assigned_status_activity",
            "assigned_analyst_id",
            "status",
            "last_activity_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, server_default=func.gen_random_uuid())
    case_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="open", index=True
    )
    assigned_analyst_id: Mapped[UUID | None] = mapped_column(ForeignKey("analysts.id"), index=True)
    assignee: Mapped[UUID | None] = mapped_column(ForeignKey("analysts.id"), index=True)
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        CheckConstraint("source IN ('rule', 'model', 'hybrid')", name="ck_alerts_source"),
        CheckConstraint("severity IN ('low', 'medium', 'high')", name="ck_alerts_severity"),
        CheckConstraint("tier IN ('low', 'med', 'high')", name="ck_alerts_tier"),
        CheckConstraint("status IN ('open', 'acknowledged', 'dismissed')", name="ck_alerts_status"),
        Index("ix_alerts_status_created", "status", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, server_default=func.gen_random_uuid())
    transaction_id: Mapped[UUID] = mapped_column(
        ForeignKey("transactions.id"), nullable=False, index=True
    )
    source: Mapped[str] = mapped_column(String(12), nullable=False)
    rule_key: Mapped[str | None] = mapped_column(String(80), index=True)
    rule_id: Mapped[UUID | None] = mapped_column(ForeignKey("rules.id"), index=True)
    severity: Mapped[str] = mapped_column(String(12), nullable=False, index=True)
    tier: Mapped[str] = mapped_column(String(8), nullable=False, server_default="med", index=True)
    priority: Mapped[str | None] = mapped_column(String(24), index=True)
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    sla_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    model_version: Mapped[str | None] = mapped_column(String(64))
    automation_action: Mapped[str | None] = mapped_column(String(120))
    incident_ref: Mapped[str | None] = mapped_column(String(80), unique=True, index=True)
    risk_score: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="open", index=True
    )
    risk_factors: Mapped[list[dict[str, Any]] | dict[str, Any]] = mapped_column(
        JSON_VALUE, nullable=False, server_default="[]"
    )
    explanation: Mapped[dict[str, Any]] = mapped_column(
        JSON_VALUE, nullable=False, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    case_id: Mapped[UUID | None] = mapped_column(ForeignKey("cases.id"), index=True)


class AlertFeedback(Base):
    __tablename__ = "alert_feedback"
    __table_args__ = (
        CheckConstraint(
            "label IN ('true_fraud', 'false_positive')", name="ck_alert_feedback_label"
        ),
        Index("ix_alert_feedback_alert_created", "alert_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, server_default=func.gen_random_uuid())
    alert_id: Mapped[UUID] = mapped_column(ForeignKey("alerts.id"), nullable=False, index=True)
    analyst_id: Mapped[UUID] = mapped_column(ForeignKey("analysts.id"), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(20), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class ModelVersion(Base):
    __tablename__ = "model_versions"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, server_default=func.gen_random_uuid())
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    version: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    trained_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False, server_default="{}")
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false", index=True
    )


class Rule(Base):
    __tablename__ = "rules"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, server_default=func.gen_random_uuid())
    key: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    params: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False, server_default="{}")


class Settings(Base):
    __tablename__ = "settings"
    __table_args__ = (CheckConstraint("id = 1", name="ck_settings_single_row"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    threshold_medium: Mapped[int] = mapped_column(Integer, nullable=False, server_default="40")
    threshold_high: Mapped[int] = mapped_column(Integer, nullable=False, server_default="75")
    notifications: Mapped[dict[str, Any]] = mapped_column(
        JSON_VALUE, nullable=False, server_default='{"email":true,"inApp":true,"sms":false}'
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CaseAlert(Base):
    __tablename__ = "case_alerts"
    __table_args__ = (Index("ix_case_alerts_alert_id", "alert_id"),)

    case_id: Mapped[UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), primary_key=True
    )
    alert_id: Mapped[UUID] = mapped_column(
        ForeignKey("alerts.id", ondelete="CASCADE"), primary_key=True
    )


class AccountLink(Base):
    __tablename__ = "account_links"
    __table_args__ = (
        UniqueConstraint(
            "source_account_id",
            "target_account_id",
            "type",
            "evidence",
            name="uq_account_links_evidence",
        ),
        CheckConstraint(
            "type IN ('fund_transfer', 'shared_ip', 'shared_device')", name="ck_account_links_type"
        ),
        Index("ix_account_links_source_last_seen", "source_account_id", "last_seen_at"),
        Index("ix_account_links_target", "target_account_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, server_default=func.gen_random_uuid())
    source_account_id: Mapped[UUID] = mapped_column(
        ForeignKey("accounts.id"), nullable=False, index=True
    )
    target_account_id: Mapped[UUID] = mapped_column(
        ForeignKey("accounts.id"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_created_at", "created_at"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, server_default=func.gen_random_uuid())
    actor_id: Mapped[UUID | None] = mapped_column(ForeignKey("analysts.id"), index=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    entity_id: Mapped[UUID | None] = mapped_column(index=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )


class SimulationLabel(Base):
    __tablename__ = "sim_labels"
    __table_args__ = (
        CheckConstraint(
            "pattern IS NULL OR pattern IN "
            "('over_10x_average', 'new_beneficiary_high_amount', "
            "'new_device_transfer', 'multi_hop')",
            name="ck_sim_labels_pattern",
        ),
    )

    idempotency_key: Mapped[str] = mapped_column(String(255), primary_key=True)
    is_fraud: Mapped[bool] = mapped_column(Boolean, nullable=False)
    pattern: Mapped[str | None] = mapped_column(String(40))
