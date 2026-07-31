"""add job_item error_code and timestamps

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-31 20:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: str | Sequence[str] | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("job_item") as batch_op:
        batch_op.add_column(sa.Column("error_code", sa.String(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            )
        )
        batch_op.add_column(sa.Column("ignored_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_index("ix_job_item_error_code", ["error_code"])


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("job_item") as batch_op:
        batch_op.drop_index("ix_job_item_error_code")
        batch_op.drop_column("ignored_at")
        batch_op.drop_column("created_at")
        batch_op.drop_column("error_code")
