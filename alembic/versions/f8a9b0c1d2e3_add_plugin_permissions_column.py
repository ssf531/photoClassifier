"""add plugin permissions column

Revision ID: f8a9b0c1d2e3
Revises: e7f8a9b0c1d2
Create Date: 2026-07-31 11:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f8a9b0c1d2e3"
down_revision: str | Sequence[str] | None = "e7f8a9b0c1d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("plugin") as batch_op:
        batch_op.add_column(
            sa.Column("permissions", sa.JSON(), nullable=False, server_default="[]")
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("plugin") as batch_op:
        batch_op.drop_column("permissions")
