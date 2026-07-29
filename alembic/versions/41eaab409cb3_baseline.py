"""baseline

Revision ID: 41eaab409cb3
Revises:
Create Date: 2026-07-29 12:34:05.511513

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "41eaab409cb3"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
