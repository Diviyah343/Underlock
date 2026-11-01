"""Initial Underlock schema."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.create_table(
        "analysts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("analyst_code", sa.String(32), nullable=False, unique=True),
        sa.Column("role", sa.String(80), nullable=False),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
    )
    op.create_table(
        "accounts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("external_ref", sa.String(100), nullable=False, unique=True),
        sa.Column("jurisdiction", sa.String(8), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("avg_90d_outflow", sa.Numeric(18, 2)),
    )
    op.create_index("ix_accounts_external_ref", "accounts", ["external_ref"])
    op.create_index("ix_accounts_jurisdiction", "accounts", ["jurisdiction"])
    op.create_index("ix_accounts_created_at", "accounts", ["created_at"])
    op.create_table(
        "beneficiaries",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("accounts.id"),
            nullable=False,
        ),
        sa.Column("counterparty_ref", sa.String(100), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_beneficiaries_account_id", "beneficiaries", ["account_id"])
    op.create_index(
        "ix_beneficiaries_account_created", "beneficiaries", ["account_id", "created_at"]
    )
    op.create_table(
        "devices",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("fingerprint", sa.String(256), nullable=False, unique=True),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_devices_first_seen_at", "devices", ["first_seen_at"])
    op.create_table(
        "rules",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("key", sa.String(80), nullable=False, unique=True),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "params", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
    )
    op.create_table(
        "settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.CheckConstraint("id = 1", name="ck_settings_single_row"),
        sa.Column("threshold_medium", sa.Integer(), server_default="40", nullable=False),
        sa.Column("threshold_high", sa.Integer(), server_default="75", nullable=False),
        sa.Column(
            "notifications",
            postgresql.JSONB(),
            server_default=sa.text(
                "jsonb_build_object('email', true, 'inApp', true, 'sms', false)"
            ),
            nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "model_versions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("version", sa.String(64), nullable=False, unique=True),
        sa.Column("trained_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "metrics", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column("is_active", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.create_index("ix_model_versions_trained_at", "model_versions", ["trained_at"])
    op.create_index("ix_model_versions_is_active", "model_versions", ["is_active"])
    op.create_table(
        "transactions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("idempotency_key", sa.String(255), nullable=False, unique=True),
        sa.Column("tx_hash", sa.String(256), nullable=False),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("accounts.id"),
            nullable=False,
        ),
        sa.Column(
            "counterparty_account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("accounts.id")
        ),
        sa.Column(
            "beneficiary_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("beneficiaries.id")
        ),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("jurisdiction", sa.String(8), nullable=False),
        sa.Column("ip_address", sa.String(45)),
        sa.Column("device_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("devices.id")),
        sa.Column("direction", sa.String(8), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("risk_score", sa.Integer()),
        sa.Column("status", sa.String(16), server_default="cleared", nullable=False),
        sa.Column("model_version", sa.String(64)),
        sa.CheckConstraint("direction IN ('inflow', 'outflow')", name="ck_transactions_direction"),
        sa.CheckConstraint(
            "status IN ('cleared', 'review', 'flagged')", name="ck_transactions_status"
        ),
    )
    for column in (
        "tx_hash",
        "account_id",
        "counterparty_account_id",
        "beneficiary_id",
        "jurisdiction",
        "device_id",
        "occurred_at",
        "status",
    ):
        op.create_index(f"ix_transactions_{column}", "transactions", [column])
    op.create_index(
        "ix_transactions_account_occurred", "transactions", ["account_id", "occurred_at"]
    )
    op.create_table(
        "cases",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("case_code", sa.String(32), nullable=False, unique=True),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("status", sa.String(20), server_default="open", nullable=False),
        sa.Column(
            "assigned_analyst_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("analysts.id")
        ),
        sa.Column(
            "opened_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "last_activity_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("status IN ('open', 'under_review', 'closed')", name="ck_cases_status"),
    )
    op.create_index("ix_cases_assigned_analyst_id", "cases", ["assigned_analyst_id"])
    op.create_index("ix_cases_status", "cases", ["status"])
    op.create_index("ix_cases_opened_at", "cases", ["opened_at"])
    op.create_index("ix_cases_last_activity_at", "cases", ["last_activity_at"])
    op.create_index("ix_cases_status_activity", "cases", ["status", "last_activity_at"])
    op.create_table(
        "alerts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "transaction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("transactions.id"),
            nullable=False,
        ),
        sa.Column("source", sa.String(12), nullable=False),
        sa.Column("rule_key", sa.String(80)),
        sa.Column("severity", sa.String(12), nullable=False),
        sa.Column("risk_score", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), server_default="open", nullable=False),
        sa.Column(
            "explanation", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cases.id")),
        sa.CheckConstraint("source IN ('rule', 'model', 'hybrid')", name="ck_alerts_source"),
        sa.CheckConstraint("severity IN ('low', 'medium', 'high')", name="ck_alerts_severity"),
        sa.CheckConstraint(
            "status IN ('open', 'acknowledged', 'dismissed')", name="ck_alerts_status"
        ),
    )
    for column in ("transaction_id", "rule_key", "severity", "status", "created_at", "case_id"):
        op.create_index(f"ix_alerts_{column}", "alerts", [column])
    op.create_index("ix_alerts_status_created", "alerts", ["status", "created_at"])
    op.create_table(
        "alert_feedback",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "alert_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("alerts.id"), nullable=False
        ),
        sa.Column(
            "analyst_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analysts.id"),
            nullable=False,
        ),
        sa.Column("label", sa.String(20), nullable=False),
        sa.Column("note", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "label IN ('true_fraud', 'false_positive')", name="ck_alert_feedback_label"
        ),
    )
    for column in ("alert_id", "analyst_id", "created_at"):
        op.create_index(f"ix_alert_feedback_{column}", "alert_feedback", [column])
    op.create_index("ix_alert_feedback_alert_created", "alert_feedback", ["alert_id", "created_at"])
    op.create_table(
        "case_alerts",
        sa.Column(
            "case_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("cases.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "alert_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("alerts.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_index("ix_case_alerts_alert_id", "case_alerts", ["alert_id"])
    op.create_table(
        "account_links",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "source_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("accounts.id"),
            nullable=False,
        ),
        sa.Column(
            "target_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("accounts.id"),
            nullable=False,
        ),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2)),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "source_account_id",
            "target_account_id",
            "type",
            "evidence",
            name="uq_account_links_evidence",
        ),
        sa.CheckConstraint(
            "type IN ('fund_transfer', 'shared_ip', 'shared_device')", name="ck_account_links_type"
        ),
    )
    for column in ("source_account_id", "target_account_id", "last_seen_at"):
        op.create_index(f"ix_account_links_{column}", "account_links", [column])
    op.create_index(
        "ix_account_links_source_last_seen", "account_links", ["source_account_id", "last_seen_at"]
    )


def downgrade() -> None:
    for table in (
        "account_links",
        "case_alerts",
        "alert_feedback",
        "alerts",
        "cases",
        "transactions",
        "model_versions",
        "settings",
        "rules",
        "devices",
        "beneficiaries",
        "accounts",
        "analysts",
    ):
        op.drop_table(table)
