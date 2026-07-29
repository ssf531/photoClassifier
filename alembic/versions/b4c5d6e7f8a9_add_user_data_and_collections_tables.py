"""add user_data, collection, collection_item, smart_collection_rule tables

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-07-29 20:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b4c5d6e7f8a9"
down_revision: str | Sequence[str] | None = "a3b4c5d6e7f8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "user_data",
        sa.Column("photo_id", sa.Uuid(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("favourite", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.String(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["photo_id"], ["photo.id"]),
        sa.PrimaryKeyConstraint("photo_id"),
    )
    op.create_table(
        "collection",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "smart_collection_rule",
        sa.Column("collection_id", sa.Uuid(), nullable=False),
        sa.Column("search_query", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["collection_id"], ["collection.id"]),
        sa.PrimaryKeyConstraint("collection_id"),
    )
    op.create_table(
        "collection_item",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("collection_id", sa.Uuid(), nullable=False),
        sa.Column("photo_id", sa.Uuid(), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["collection_id"], ["collection.id"]),
        sa.ForeignKeyConstraint(["photo_id"], ["photo.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("collection_id", "photo_id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("collection_item")
    op.drop_table("smart_collection_rule")
    op.drop_table("collection")
    op.drop_table("user_data")
