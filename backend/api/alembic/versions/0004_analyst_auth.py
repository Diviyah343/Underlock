"""Add analyst password hashes."""

import sqlalchemy as sa
from alembic import op

revision = "0004_analyst_auth"
down_revision = "0003_investigation_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("analysts", sa.Column("password_hash", sa.String(256), nullable=True))


def downgrade() -> None:
    op.drop_column("analysts", "password_hash")
