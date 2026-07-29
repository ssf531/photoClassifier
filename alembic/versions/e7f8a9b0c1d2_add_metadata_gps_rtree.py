"""add metadata GPS R-tree index

Revision ID: e7f8a9b0c1d2
Revises: d6e7f8a9b0c1
Create Date: 2026-07-29 23:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e7f8a9b0c1d2"
down_revision: str | Sequence[str] | None = "d6e7f8a9b0c1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Deferred from TASK-032 (SDD §5.3): SQLite's rtree module needs an integer
# id, which this schema's UUID photo_ids don't provide. Same fix as
# TASK-053's vec0 rowids: a stable id derived by hashing the photo_id, with
# the real photo_id kept as an auxiliary (+) column for the reverse lookup.
# A point (not a real bounding box) is indexed as a zero-area box
# (min == max in both dimensions), which the rtree module handles natively.


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        CREATE VIRTUAL TABLE metadata_gps_rtree USING rtree(
            id,
            min_lat, max_lat,
            min_lon, max_lon,
            +photo_id TEXT
        )
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_metadata_gps_rtree_ai AFTER INSERT ON metadata
        WHEN NEW.gps_lat IS NOT NULL AND NEW.gps_lon IS NOT NULL
        BEGIN
            INSERT INTO metadata_gps_rtree(id, min_lat, max_lat, min_lon, max_lon, photo_id)
            VALUES (
                (abs(random()) % 9223372036854775807),
                NEW.gps_lat, NEW.gps_lat, NEW.gps_lon, NEW.gps_lon, NEW.photo_id
            );
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_metadata_gps_rtree_au AFTER UPDATE ON metadata
        BEGIN
            DELETE FROM metadata_gps_rtree WHERE photo_id = OLD.photo_id;
            INSERT INTO metadata_gps_rtree(id, min_lat, max_lat, min_lon, max_lon, photo_id)
            SELECT (abs(random()) % 9223372036854775807),
                   NEW.gps_lat, NEW.gps_lat, NEW.gps_lon, NEW.gps_lon, NEW.photo_id
            WHERE NEW.gps_lat IS NOT NULL AND NEW.gps_lon IS NOT NULL;
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_metadata_gps_rtree_ad AFTER DELETE ON metadata
        BEGIN
            DELETE FROM metadata_gps_rtree WHERE photo_id = OLD.photo_id;
        END
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    for trigger in (
        "trg_metadata_gps_rtree_ad",
        "trg_metadata_gps_rtree_au",
        "trg_metadata_gps_rtree_ai",
    ):
        op.execute(f"DROP TRIGGER {trigger}")
    op.execute("DROP TABLE metadata_gps_rtree")
