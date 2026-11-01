from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from shared.constants import (
    AccountLinkType,
    AlertSeverity,
    AlertSource,
    AlertStatus,
    CaseStatus,
    FeedbackLabel,
    TransactionDirection,
    TransactionStatus,
    TransactionType,
)

AlertTier = Literal["low", "med", "high"]
AlertDecision = Literal["false_positive", "confirmed_fraud"]


class ContractModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"] = "ok"
    database: Literal["ok", "error"] = "ok"
    redis: Literal["ok", "error"] = "ok"


class AnalystLogin(BaseModel):
    analyst_code: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=1, max_length=256)


class AnalystToken(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: datetime
    analyst_id: str


class AnalystLogoutResponse(BaseModel):
    status: Literal["logged_out"] = "logged_out"


class TransactionRead(ContractModel):
    id: UUID
    tx_hash: str
    account_id: UUID
    counterparty_account_id: UUID | None = None
    beneficiary_id: UUID | None = None
    amount: Decimal
    currency: str
    jurisdiction: str
    direction: TransactionDirection
    tx_type: TransactionType
    oldbalance_org: Decimal | None = None
    newbalance_org: Decimal | None = None
    oldbalance_dest: Decimal | None = None
    newbalance_dest: Decimal | None = None
    occurred_at: datetime
    ingested_at: datetime
    persisted_at: datetime | None = None
    risk_score: int | None = None
    status: TransactionStatus


class TransactionPage(BaseModel):
    items: list[TransactionRead] = []
    status_counts: dict[TransactionStatus, int] = {
        TransactionStatus.CLEARED: 0,
        TransactionStatus.REVIEW: 0,
        TransactionStatus.FLAGGED: 0,
    }
    total: int = 0
    limit: int = 100
    offset: int = 0


class TransactionVolumePoint(BaseModel):
    timestamp: datetime
    volume: Decimal
    transaction_count: int


class FraudRatePoint(BaseModel):
    timestamp: datetime
    fraud_rate: float


class TransactionMetrics(BaseModel):
    range: Literal["24h", "1h", "live"]
    throughput_tx_s: float
    total_count: int
    volume_series: list[TransactionVolumePoint]
    fraud_rate_series: list[FraudRatePoint]
    fraud_rate_threshold: float = Field(ge=0, le=1)


class FeatureContribution(BaseModel):
    feature: str
    contribution: float


class AlertRiskFactor(BaseModel):
    title: str
    weight_pct: int = Field(ge=0, le=100)
    description: str


class AlertRead(ContractModel):
    id: UUID
    transaction_id: UUID
    source: AlertSource
    rule_key: str | None = None
    severity: AlertSeverity
    tier: AlertTier | None = None
    priority: str | None = None
    risk_score: int
    status: AlertStatus
    opened_at: datetime | None = None
    sla_deadline: datetime | None = None
    model_version: str | None = None
    automation_action: str | None = None
    incident_ref: str | None = None
    risk_factors: list[AlertRiskFactor] = []
    explanation: dict[str, Any] = {}
    created_at: datetime
    case_id: UUID | None = None


class AlertListItem(AlertRead):
    pass


class AlertPage(BaseModel):
    items: list[AlertListItem] = []
    page: int = 1
    page_size: int = 25
    total: int = 0


class AccountSummary(BaseModel):
    id: UUID
    external_ref: str
    name: str | None = None
    kyc_ref: str | None = None
    risk_index: int = 0
    jurisdiction: str | None = None


class AlertDetailRead(AlertRead):
    sla_remaining_seconds: int = 0
    flagged_account: AccountSummary | None = None
    trigger_transaction: TransactionRead | None = None
    last_5_transactions: list[TransactionRead] = []
    queue_time: int = 0


class AlertUpdate(BaseModel):
    status: AlertStatus


class AlertFeedbackCreate(BaseModel):
    analyst_id: UUID
    label: FeedbackLabel
    note: str | None = None


class AlertFeedbackRead(AlertFeedbackCreate):
    id: UUID
    alert_id: UUID
    created_at: datetime


class AlertDecisionRequest(BaseModel):
    decision: AlertDecision
    note: str | None = None


class AlertDecisionResponse(BaseModel):
    alert_id: UUID
    status: AlertStatus
    decision: AlertDecision
    feedback_id: UUID
    audit_log_id: UUID


class AlertExplanation(BaseModel):
    alert_id: UUID
    contributions: list[FeatureContribution] = []


class CaseCreate(BaseModel):
    title: str
    assigned_analyst_id: UUID | None = None
    alert_ids: list[UUID] = []


class CaseRead(ContractModel):
    id: UUID
    case_code: str
    title: str
    status: CaseStatus
    assigned_analyst_id: UUID | None = None
    opened_at: datetime
    closed_at: datetime | None = None
    last_activity_at: datetime


class CasePage(BaseModel):
    items: list[CaseRead] = []
    total: int = 0


class CaseStats(BaseModel):
    open: int = 0
    under_review: int = 0
    closed: int = 0


class InvestigationCreate(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    alert_ids: list[UUID] = Field(min_length=1)
    assignee_id: UUID | None = None


class InvestigationRead(BaseModel):
    id: UUID
    case_code: str
    title: str
    status: CaseStatus
    linked_alerts: int
    combined_exposure: Decimal
    assignee: AnalystRead | None = None
    last_activity: datetime
    created_at: datetime
    closed_at: datetime | None = None


class InvestigationPage(BaseModel):
    items: list[InvestigationRead] = []
    total: int = 0
    page: int = 1
    page_size: int = 25


class InvestigationStats(BaseModel):
    open_count: int = 0
    total_count: int = 0
    assigned_to_me: int = 0
    avg_resolution_time_seconds: float = 0.0


class InvestigationGraphNode(BaseModel):
    id: UUID
    external_ref: str
    name: str | None = None


class InvestigationGraphEdge(BaseModel):
    source: UUID
    target: UUID
    type: Literal["fund_transfer", "shared_ip", "shared_device"]
    transaction_count: int = 0
    amount: Decimal | None = None
    shared_value: str | None = None
    last_seen_at: datetime | None = None


class InvestigationGraph(BaseModel):
    nodes: list[InvestigationGraphNode] = []
    edges: list[InvestigationGraphEdge] = []
    connections: list[InvestigationGraphEdge] = []


class LinkedAccountRead(BaseModel):
    account_id: UUID
    external_ref: str
    link_type: AccountLinkType
    amount: Decimal | None = None
    last_seen_at: datetime | None = None


class CaseLinkedAccounts(BaseModel):
    items: list[LinkedAccountRead] = []
    combined_exposure: Decimal = Decimal("0")


class SettingsRead(BaseModel):
    threshold_medium: int = 40
    threshold_high: int = 75
    notifications: dict[str, bool] = {"email": True, "inApp": True, "sms": False}
    updated_at: datetime | None = None


class SettingsUpdate(BaseModel):
    threshold_medium: int = 40
    threshold_high: int = 75
    notifications: dict[str, bool] = {"email": True, "inApp": True, "sms": False}


class AnalystRead(BaseModel):
    id: UUID
    name: str
    analyst_code: str
    role: str
    email: str


class TransactionIngestPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tx_hash: str = Field(min_length=1, max_length=256)
    account_id: UUID
    counterparty_account_id: UUID | None = None
    beneficiary_id: UUID | None = None
    amount: Decimal = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3, pattern="^[A-Z]{3}$")
    jurisdiction: str = Field(min_length=2, max_length=8)
    ip_address: str | None = None
    device_id: UUID | None = None
    direction: TransactionDirection
    tx_type: TransactionType
    occurred_at: AwareDatetime
    oldbalance_org: Decimal | None = Field(default=None, ge=0)
    newbalance_org: Decimal | None = Field(default=None, ge=0)
    oldbalance_dest: Decimal | None = Field(default=None, ge=0)
    newbalance_dest: Decimal | None = Field(default=None, ge=0)
    account_external_ref: str | None = Field(default=None, min_length=1, max_length=100)
    counterparty_external_ref: str | None = Field(default=None, min_length=1, max_length=100)
    counterparty_jurisdiction: str | None = Field(default=None, min_length=2, max_length=8)
    beneficiary_ref: str | None = Field(default=None, min_length=1, max_length=100)
    beneficiary_created_at: AwareDatetime | None = None
    device_fingerprint: str | None = Field(default=None, min_length=1, max_length=256)
    device_first_seen_at: AwareDatetime | None = None
    avg_90d_outflow: Decimal | None = Field(default=None, ge=0)

    @field_validator(
        "tx_hash",
        "account_external_ref",
        "counterparty_external_ref",
        "beneficiary_ref",
        "device_fingerprint",
    )
    @classmethod
    def strip_nonempty_identifiers(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value

    @field_validator("occurred_at", "beneficiary_created_at", "device_first_seen_at", mode="before")
    @classmethod
    def require_iso_timestamp(cls, value: Any) -> Any:
        if value is None or isinstance(value, datetime):
            return value
        if not isinstance(value, str):
            raise ValueError("timestamp must be an ISO 8601 string")
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("timestamp must be an ISO 8601 string") from exc
        return value


class IngestTransaction(TransactionIngestPayload):
    idempotency_key: str = Field(min_length=1, max_length=255)

    @field_validator("idempotency_key")
    @classmethod
    def strip_idempotency_key(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value


class IngestItemResult(BaseModel):
    idempotency_key: str
    status: str
    duplicate: bool


class IngestResponse(BaseModel):
    accepted_count: int
    duplicate_count: int
    items: list[IngestItemResult]
