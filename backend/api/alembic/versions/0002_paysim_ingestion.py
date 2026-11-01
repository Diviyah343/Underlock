"""Add PaySim fields, persistence timestamps, and simulation labels."""

import sqlalchemy as sa
from alembic import op

revision = "0002_paysim_ingestion"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "transactions",
        sa.Column("tx_type", sa.String(16), server_default="PAYMENT", nullable=False),
    )
    op.add_column("transactions", sa.Column("oldbalance_org", sa.Numeric(18, 2)))
    op.add_column("transactions", sa.Column("newbalance_org", sa.Numeric(18, 2)))
    op.add_column("transactions", sa.Column("oldbalance_dest", sa.Numeric(18, 2)))
    op.add_column("transactions", sa.Column("newbalance_dest", sa.Numeric(18, 2)))
    op.add_column(
        "transactions",
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.add_column("transactions", sa.Column("persisted_at", sa.DateTime(timezone=True)))
    op.create_check_constraint(
        "ck_transactions_tx_type",
        "transactions",
        "tx_type IN ('PAYMENT', 'TRANSFER', 'CASH_OUT', 'CASH_IN', 'DEBIT')",
    )
    op.create_index("ix_transactions_ingested_at", "transactions", ["ingested_at"])
    op.create_index("ix_transactions_persisted_at", "transactions", ["persisted_at"])
    op.create_index("ix_transactions_ip_address", "transactions", ["ip_address"])
    op.create_table(
        "sim_labels",
        sa.Column("idempotency_key", sa.String(255), primary_key=True),
        sa.Column("is_fraud", sa.Boolean(), nullable=False),
        sa.Column("pattern", sa.String(40)),
        sa.CheckConstraint(
            "pattern IS NULL OR pattern IN "
            "('over_10x_average', 'new_beneficiary_high_amount', "
            "'new_device_transfer', 'multi_hop')",
            name="ck_sim_labels_pattern",
        ),
    )


def downgrade() -> None:
    op.drop_table("sim_labels")
    op.drop_index("ix_transactions_ip_address", table_name="transactions")
    op.drop_index("ix_transactions_persisted_at", table_name="transactions")
    op.drop_index("ix_transactions_ingested_at", table_name="transactions")
    op.drop_constraint("ck_transactions_tx_type", "transactions", type_="check")
    for column in (
        "persisted_at",
        "ingested_at",
        "newbalance_dest",
        "oldbalance_dest",
        "newbalance_org",
        "oldbalance_org",
        "tx_type",
    ):
        op.drop_column("transactions", column)
