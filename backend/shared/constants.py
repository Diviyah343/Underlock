from enum import StrEnum


class TransactionDirection(StrEnum):
    INFLOW = "inflow"
    OUTFLOW = "outflow"


class TransactionType(StrEnum):
    PAYMENT = "PAYMENT"
    TRANSFER = "TRANSFER"
    CASH_OUT = "CASH_OUT"
    CASH_IN = "CASH_IN"
    DEBIT = "DEBIT"


class FraudPattern(StrEnum):
    OVER_10X_AVERAGE = "over_10x_average"
    NEW_BENEFICIARY_HIGH_AMOUNT = "new_beneficiary_high_amount"
    NEW_DEVICE_TRANSFER = "new_device_transfer"
    MULTI_HOP = "multi_hop"


class TransactionStatus(StrEnum):
    CLEARED = "cleared"
    REVIEW = "review"
    FLAGGED = "flagged"


TRANSACTION_EVENT_CHANNEL = "tx:events"
ALERT_EVENT_CHANNEL = "alert:events"


class AlertSource(StrEnum):
    RULE = "rule"
    MODEL = "model"
    HYBRID = "hybrid"


class AlertSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AlertStatus(StrEnum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    DISMISSED = "dismissed"


class CaseStatus(StrEnum):
    OPEN = "open"
    UNDER_REVIEW = "under_review"
    CLOSED = "closed"


class FeedbackLabel(StrEnum):
    TRUE_FRAUD = "true_fraud"
    FALSE_POSITIVE = "false_positive"


class AccountLinkType(StrEnum):
    FUND_TRANSFER = "fund_transfer"
    SHARED_IP = "shared_ip"
    SHARED_DEVICE = "shared_device"
