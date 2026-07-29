"""add embedding_index vec0 table

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
Create Date: 2026-07-29 22:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d6e7f8a9b0c1"
down_revision: str | Sequence[str] | None = "c5d6e7f8a9b0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 512 matches the only v1 embedding provider (CLIP ViT-B/32, TASK-041). A
# future differently-dimensioned model would need its own vec0 table --
# vec0 fixes one dimension per table across all its partitions.
EMBEDDING_DIMENSIONS = 512


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        f"""
        CREATE VIRTUAL TABLE embedding_index USING vec0(
            embedding float[{EMBEDDING_DIMENSIONS}] distance_metric=cosine,
            vector_space text partition key,
            +vector_key TEXT,
            +photo_id TEXT
        )
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TABLE embedding_index")
