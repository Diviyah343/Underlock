"""Add columns required by the browser UI contract."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005_ui_contract_schema"
down_revision = "0004_analyst_auth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("accounts", sa.Column("name", sa.String(160), nullable=True))
    op.add_column("accounts", sa.Column("kyc_ref", sa.String(80), nullable=True))
    op.add_column(
        "accounts",
        sa.Column("risk_index", sa.Integer(), server_default="0", nullable=False),
    )
    op.create_check_constraint(
        "ck_accounts_risk_index",
        "accounts",
        "risk_index BETWEEN 0 AND 100",
    )
    op.create_index("ix_accounts_kyc_ref", "accounts", ["kyc_ref"])

    op.add_column("transactions", sa.Column("ip", sa.String(45), nullable=True))
    op.add_column(
        "transactions", sa.Column("location_country", sa.String(64), nullable=True)
    )
    op.add_column(
        "transactions", sa.Column("device_signature", sa.String(256), nullable=True)
    )
    op.add_column(
        "transactions", sa.Column("origin_channel", sa.String(40), nullable=True)
    )
    op.add_column(
        "transactions", sa.Column("beneficiary_entity", sa.String(160), nullable=True)
    )
    op.add_column(
        "transactions", sa.Column("beneficiary_bank", sa.String(160), nullable=True)
    )
    for column in (
        "ip",
        "location_country",
        "origin_channel",
        "beneficiary_entity",
        "beneficiary_bank",
    ):
        op.create_index(f"ix_transactions_{column}", "transactions", [column])

    op.add_column(
        "cases",
        sa.Column("assignee", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_cases_assignee_analysts",
        "cases",
        "analysts",
        ["assignee"],
        ["id"],
    )
    op.add_column(
        "cases",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_cases_assignee", "cases", ["assignee"])
    op.create_index("ix_cases_created_at", "cases", ["created_at"])

    op.add_column(
        "alerts",
        sa.Column("rule_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "alerts",
        sa.Column("tier", sa.String(8), server_default="med", nullable=False),
    )
    op.add_column("alerts", sa.Column("priority", sa.String(24), nullable=True))
    op.add_column(
        "alerts",
        sa.Column(
            "opened_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.add_column(
        "alerts", sa.Column("sla_deadline", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("alerts", sa.Column("model_version", sa.String(64), nullable=True))
    op.add_column(
        "alerts", sa.Column("automation_action", sa.String(120), nullable=True)
    )
    op.add_column("alerts", sa.Column("incident_ref", sa.String(80), nullable=True))
    op.add_column(
        "alerts",
        sa.Column(
            "risk_factors",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_alerts_tier",
        "alerts",
        "tier IN ('low', 'med', 'high')",
    )
    op.create_index("ix_alerts_rule_id", "alerts", ["rule_id"])
    op.create_index("ix_alerts_tier", "alerts", ["tier"])
    op.create_index("ix_alerts_priority", "alerts", ["priority"])
    op.create_index("ix_alerts_opened_at", "alerts", ["opened_at"])
    op.create_index("ix_alerts_sla_deadline", "alerts", ["sla_deadline"])
    op.create_index(
        "ix_alerts_incident_ref", "alerts", ["incident_ref"], unique=True
    )

    op.create_table(
        "audit_log",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("entity_type", sa.String(40), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "details",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["actor_id"], ["analysts.id"]),
    )
    op.create_index("ix_audit_log_actor_id", "audit_log", ["actor_id"])
    op.create_index("ix_audit_log_action", "audit_log", ["action"])
    op.create_index("ix_audit_log_entity_type", "audit_log", ["entity_type"])
    op.create_index("ix_audit_log_entity_id", "audit_log", ["entity_id"])
    op.create_index("ix_audit_log_created_at", "audit_log", ["created_at"])


def downgrade() -> None:
    op.drop_table("audit_log")

    for index in (
        "ix_alerts_incident_ref",
        "ix_alerts_sla_deadline",
        "ix_alerts_opened_at",
        "ix_alerts_priority",
        "ix_alerts_tier",
        "ix_alerts_rule_id",
    ):
        op.drop_index(index, table_name="alerts")
    op.drop_constraint("ck_alerts_tier", "alerts", type_="check")
    op.drop_column("alerts", "risk_factors")
    op.drop_column("alerts", "incident_ref")
    op.drop_column("alerts", "automation_action")
    op.drop_column("alerts", "model_version")
    op.drop_column("alerts", "sla_deadline")
    op.drop_column("alerts", "opened_at")
    op.drop_column("alerts", "priority")
    op.drop_column("alerts", "tier")
    op.drop_constraint("fk_alerts_rule_id_rules", "alerts", type_="foreignkey")
    op.drop_column("alerts", "rule_id")

    op.drop_index("ix_cases_created_at", table_name="cases")
    op.drop_index("ix_cases_assignee", table_name="cases")
    op.drop_column("cases", "created_at")
    op.drop_constraint("fk_cases_assignee_analysts", "cases", type_="foreignkey")
    op.drop_column("cases", "assignee")

    for column in (
        "beneficiary_bank",
        "beneficiary_entity",
        "origin_channel",
        "location_country",
        "ip",
    ):
        op.drop_index(f"ix_transactions_{column}", table_name="transactions")
        op.drop_column("transactions", column)
    op.drop_column("transactions", "device_signature")

    op.drop_index("ix_accounts_kyc_ref", table_name="accounts")
    op.drop_constraint("ck_accounts_risk_index", "accounts", type_="check")
    op.drop_column("accounts", "risk_index")
    op.drop_column("accounts", "kyc_ref")
    op.drop_column("accounts", "name")
