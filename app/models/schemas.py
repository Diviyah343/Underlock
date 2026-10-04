from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class AlertTier(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"


class AlertDisposition(StrEnum):
    confirmed_fraud = "confirmed_fraud"
    false_positive = "false_positive"


class RecentActivity(BaseModel):
    timestamp: datetime
    amount: float = Field(ge=0)
    route: str
    state: str


class ContributingRiskFactor(BaseModel):
    label: str
    weight: int = Field(ge=0, le=100)
    detail: str


class Alert(BaseModel):
    alert_id: str
    tier: AlertTier
    entity_type: str
    opened_at: datetime
    sla_remaining_seconds: int = Field(ge=0)
    priority: int = Field(ge=1, le=5)
    account_name: str
    account_id: str
    account_tier: str
    trigger_amount: float = Field(ge=0)
    trigger_currency: str
    location: str
    ip_address: str
    device_signature: str
    origin_channel: str
    beneficiary_entity: str
    beneficiary_bank: str
    kyc_ref: str
    risk_index: int = Field(ge=0, le=100)
    recent_activity: list[RecentActivity]
    contributing_risk_factors: list[ContributingRiskFactor]
    risk_profile: str
    ip_reputation: str
    rule_trigger: str
    incident_ref: str
    automation_status: str
    automation_active: bool
    signature: str
    analyst_notes: str
    disposition: AlertDisposition | None = None


class TransactionStatus(StrEnum):
    clear = "clear"
    review = "review"
    flagged = "flagged"


class Transaction(BaseModel):
    tx_id: str
    timestamp: datetime
    account_id: str
    amount: float = Field(ge=0)
    route: str
    jurisdiction: str
    status: TransactionStatus


class CaseStatus(StrEnum):
    open = "open"
    under_review = "under_review"
    closed = "closed"


class Case(BaseModel):
    case_id: str
    case_title: str
    linked_alerts: int = Field(ge=0)
    combined_exposure: float = Field(ge=0)
    status: CaseStatus
    assigned_analyst: str
    last_activity: datetime


class Investigation(Case):
    """Compatibility name for the existing investigations router."""


class LinkedAccountNode(BaseModel):
    account_id: str
    account_name: str
    node_type: str


class GraphRelation(StrEnum):
    fund_transfer = "fund_transfer"
    shared_ip = "shared_ip"
    shared_device = "shared_device"


class LinkedAccountEdge(BaseModel):
    source: str
    target: str
    relation: GraphRelation


class LinkedAccountGraph(BaseModel):
    nodes: list[LinkedAccountNode]
    edges: list[LinkedAccountEdge]


class RiskThresholds(BaseModel):
    low_min: int = Field(ge=0, le=100)
    low_max: int = Field(ge=0, le=100)
    medium_min: int = Field(ge=0, le=100)
    high_min: int = Field(ge=0, le=100)


class AlertRule(BaseModel):
    rule_id: str
    name: str
    description: str
    enabled: bool


class NotificationSettings(BaseModel):
    email: bool
    in_app: bool
    sms: bool


class AccountSettings(BaseModel):
    analyst_id: str
    name: str
    role: str
    session_status: str


class DashboardSettings(BaseModel):
    risk_thresholds: RiskThresholds
    alert_rules: list[AlertRule]
    notifications: NotificationSettings
    account: AccountSettings


Settings = DashboardSettings
