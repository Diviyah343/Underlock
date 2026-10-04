from app.models.schemas import (
    Alert,
    Case,
    DashboardSettings,
    LinkedAccountGraph,
    Transaction,
)


PRIMARY_ACCOUNT_ID = "acct_2048"
PRIMARY_ACCOUNT_NAME = "Aurelia Export Holdings"
PRIMARY_BASELINE_TRANSACTION_AVERAGE = 2000.00

transactions = [
    Transaction(
        tx_id="tx_1001",
        timestamp="2026-09-14T09:18:00Z",
        # account_id=PRIMARY_ACCOUNT_ID,
        amount=10000.00,
        route="Aurelia Export Holdings -> Meridian Trade Bank",
        jurisdiction="GB -> AE",
        status="flagged",
    ),
    Transaction(
        tx_id="tx_1002",
        timestamp="2026-09-14T09:21:00Z",
        account_id=PRIMARY_ACCOUNT_ID,
        amount=2400.00,
        route="Aurelia Export Holdings -> Northstar Logistics",
        jurisdiction="GB -> NL",
        status="review",
    ),
    Transaction(
        tx_id="tx_1003",
        timestamp="2026-09-14T09:26:00Z",
        account_id="acct_7712",
        amount=1850.00,
        route="Aurelia Export Holdings -> Kestrel Trading",
        jurisdiction="GB -> CY",
        status="clear",
    ),
]

alerts = [
    Alert(
        alert_id="alt_501",
        tier="high",
        entity_type="corporate_account",
        opened_at="2026-09-14T09:19:00Z",
        sla_remaining_seconds=68400,
        priority=1,
        account_name=PRIMARY_ACCOUNT_NAME,
        account_id=PRIMARY_ACCOUNT_ID,
        account_tier="enterprise",
        trigger_amount=10000.00,
        trigger_currency="USD",
        location="London, GB",
        ip_address="198.51.100.24",
        device_signature="dev_a91f7c",
        origin_channel="online_banking",
        beneficiary_entity="Meridian Trade Bank",
        beneficiary_bank="MTB-GB-0042",
        kyc_ref="KYC-2048-2026",
        risk_index=87,
        recent_activity=[
            {
                "timestamp": "2026-09-14T09:18:00Z",
                "amount": 10000.00,
                "route": "Aurelia Export Holdings -> Meridian Trade Bank",
                "state": "flagged",
            },
            {
                "timestamp": "2026-09-14T09:21:00Z",
                "amount": 2400.00,
                "route": "Aurelia Export Holdings -> Northstar Logistics",
                "state": "review",
            },
        ],
        contributing_risk_factors=[
            {
                "label": "Amount deviation",
                "weight": 42,
                "detail": "USD 10,000 is exactly 5.0x the account baseline average of USD 2,000.",
            },
            {
                "label": "Beneficiary risk",
                "weight": 28,
                "detail": "New beneficiary in a higher-risk jurisdiction.",
            },
            {
                "label": "Shared infrastructure",
                "weight": 17,
                "detail": "IP and device signature appear on two linked accounts.",
            },
        ],
        risk_profile="Elevated cross-border activity with a sharp amount deviation.",
        ip_reputation="suspicious",
        rule_trigger="AML-07: amount exceeds 4x rolling account average",
        incident_ref="INC-2026-0914-501",
        automation_status="analyst_review_required",
        automation_active=True,
        signature="sig_7fd2a1",
        analyst_notes="Confirm beneficiary relationship and source of funds.",
    ),
    Alert(
        alert_id="alt_502",
        tier="medium",
        entity_type="linked_account",
        opened_at="2026-09-14T09:27:00Z",
        sla_remaining_seconds=172800,
        priority=3,
        account_name="Kestrel Trading Ltd",
        account_id="acct_7712",
        account_tier="standard",
        trigger_amount=1850.00,
        trigger_currency="USD",
        location="Nicosia, CY",
        ip_address="198.51.100.24",
        device_signature="dev_a91f7c",
        origin_channel="online_banking",
        beneficiary_entity=PRIMARY_ACCOUNT_NAME,
        beneficiary_bank="MTB-GB-0042",
        kyc_ref="KYC-7712-2026",
        risk_index=61,
        recent_activity=[
            {
                "timestamp": "2026-09-14T09:26:00Z",
                "amount": 1850.00,
                "route": "Aurelia Export Holdings -> Kestrel Trading",
                "state": "clear",
            }
        ],
        contributing_risk_factors=[
            {
                "label": "Shared IP",
                "weight": 35,
                "detail": "Same public IP as the primary flagged account.",
            }
        ],
        risk_profile="Linked account with shared infrastructure.",
        ip_reputation="suspicious",
        rule_trigger="AML-12: shared IP with high-tier alert",
        incident_ref="INC-2026-0914-502",
        automation_status="queued",
        automation_active=False,
        signature="sig_7712b8",
        analyst_notes="Review relationship to primary account.",
    ),
    Alert(
        alert_id="alt_503",
        tier="low",
        entity_type="corporate_account",
        opened_at="2026-09-13T15:00:00Z",
        sla_remaining_seconds=259200,
        priority=5,
        account_name="Northstar Logistics",
        account_id="acct_8821",
        account_tier="standard",
        trigger_amount=600.00,
        trigger_currency="USD",
        location="Amsterdam, NL",
        ip_address="203.0.113.18",
        device_signature="dev_4b812e",
        origin_channel="api",
        beneficiary_entity="Northstar Logistics",
        beneficiary_bank="NSL-NL-0011",
        kyc_ref="KYC-8821-2026",
        risk_index=34,
        recent_activity=[
            {
                "timestamp": "2026-09-13T14:59:00Z",
                "amount": 600.00,
                "route": "Northstar Logistics -> Payroll Services",
                "state": "clear",
            }
        ],
        contributing_risk_factors=[
            {
                "label": "New payment route",
                "weight": 18,
                "detail": "First payment to this beneficiary in 90 days.",
            }
        ],
        risk_profile="Low-risk new route.",
        ip_reputation="clean",
        rule_trigger="AML-03: new beneficiary route",
        incident_ref="INC-2026-0913-503",
        automation_status="auto_cleared",
        automation_active=False,
        signature="sig_8821c0",
        analyst_notes="No immediate action required.",
        disposition="false_positive",
    ),
]

cases = [
    Case(
        case_id="case_801",
        case_title="Aurelia Export Holdings high-value transfer",
        linked_alerts=2,
        combined_exposure=14250.00,
        status="under_review",
        assigned_analyst="Maya Chen",
        last_activity="2026-09-14T10:05:00Z",
    ),
    Case(
        case_id="case_802",
        case_title="Northstar Logistics route review",
        linked_alerts=1,
        combined_exposure=600.00,
        status="closed",
        assigned_analyst="Jon Bell",
        last_activity="2026-09-13T16:20:00Z",
    ),
]

investigations = cases

linked_account_graph = LinkedAccountGraph(
    nodes=[
        {
            "account_id": PRIMARY_ACCOUNT_ID,
            "account_name": PRIMARY_ACCOUNT_NAME,
            "node_type": "primary",
        },
        {"account_id": "acct_7712", "account_name": "Kestrel Trading Ltd", "node_type": "linked"},
        {"account_id": "acct_8821", "account_name": "Northstar Logistics", "node_type": "linked"},
    ],
    edges=[
        {"source": PRIMARY_ACCOUNT_ID, "target": "acct_7712", "relation": "shared_ip"},
        {"source": PRIMARY_ACCOUNT_ID, "target": "acct_7712", "relation": "shared_device"},
        {"source": PRIMARY_ACCOUNT_ID, "target": "acct_8821", "relation": "fund_transfer"},
    ],
)

dashboard_settings = DashboardSettings(
    risk_thresholds={"low_min": 0, "low_max": 39, "medium_min": 40, "high_min": 70},
    alert_rules=[
        {
            "rule_id": "AML-07",
            "name": "Amount deviation",
            "description": "Flag transfers exceeding four times the rolling account average.",
            "enabled": True,
        },
        {
            "rule_id": "AML-12",
            "name": "Shared infrastructure",
            "description": "Flag accounts sharing IP or device signatures.",
            "enabled": True,
        },
    ],
    notifications={"email": True, "in_app": True, "sms": False},
    account={
        "analyst_id": "an_104",
        "name": "Maya Chen",
        "role": "Senior Financial Crime Analyst",
        "session_status": "active",
    },
)
