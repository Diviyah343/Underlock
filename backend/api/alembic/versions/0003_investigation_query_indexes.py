"""Add indexes for investigation list and graph queries."""

import sqlalchemy as sa
from alembic import op

revision = "0003_investigation_indexes"
down_revision = "0002_paysim_ingestion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.create_index(
        "ix_cases_assigned_status_activity",
        "cases",
        ["assigned_analyst_id", "status", "last_activity_at"],
    )
    op.create_index(
        "ix_cases_title_trgm",
        "cases",
        [sa.text("lower(title) gin_trgm_ops")],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_cases_code_trgm",
        "cases",
        [sa.text("lower(case_code) gin_trgm_ops")],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_transactions_ip_activity_account",
        "transactions",
        ["ip_address", "occurred_at", "account_id"],
    )
    op.create_index(
        "ix_transactions_device_activity_account",
        "transactions",
        ["device_id", "occurred_at", "account_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_transactions_device_activity_account", table_name="transactions")
    op.drop_index("ix_transactions_ip_activity_account", table_name="transactions")
    op.drop_index("ix_cases_code_trgm", table_name="cases")
    op.drop_index("ix_cases_title_trgm", table_name="cases")
    op.drop_index("ix_cases_assigned_status_activity", table_name="cases")
