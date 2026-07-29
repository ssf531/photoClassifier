"""add duplicate_group and duplicate_group_member tables

Revision ID: f2b3c4d5e6a7
Revises: e1a2b3c4d5f6
Create Date: 2026-07-29 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f2b3c4d5e6a7"
down_revision: str | Sequence[str] | None = "e1a2b3c4d5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "duplicate_group",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("detection_method", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "duplicate_group_member",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("group_id", sa.Uuid(), nullable=False),
        sa.Column("photo_id", sa.Uuid(), nullable=False),
        sa.Column("similarity_score", sa.Float(), nullable=False),
        sa.Column("is_recommended_keeper", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["group_id"], ["duplicate_group.id"]),
        sa.ForeignKeyConstraint(["photo_id"], ["photo.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("group_id", "photo_id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("duplicate_group_member")
    op.drop_table("duplicate_group")
