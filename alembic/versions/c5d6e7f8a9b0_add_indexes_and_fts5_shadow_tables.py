"""add indexes and FTS5 shadow tables

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
Create Date: 2026-07-29 21:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c5d6e7f8a9b0"
down_revision: str | Sequence[str] | None = "b4c5d6e7f8a9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# GPS (metadata.gps_lat, gps_lon) R-tree indexing (SDD §5.3) is deliberately
# NOT part of this migration: SQLite's rtree module requires an integer
# rowid, which this schema's UUID primary keys don't provide, and there is
# no v1 consumer yet (the GPS bbox query builder is TASK-054, Phase 5). Build
# it alongside that task, with whatever integer-surrogate scheme its actual
# query pattern needs.


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index("ix_photo_captured_at_local", "photo", ["captured_at_local"])
    op.create_index(
        "ix_ai_result_photo_capability_current",
        "ai_result",
        ["photo_id", "capability", "is_current"],
    )
    op.create_index(
        "ix_ai_result_plugin_model_version", "ai_result", ["plugin_id", "model_version"]
    )
    # SQLite has no ALTER TABLE ADD CONSTRAINT; batch mode does the
    # copy-and-move Alembic needs to add a unique constraint after the fact.
    with op.batch_alter_table("embedding_ref") as batch_op:
        batch_op.create_unique_constraint(
            "uq_embedding_ref_photo_vector_space", ["photo_id", "vector_space"]
        )
    op.create_index("ix_duplicate_group_member_photo_id", "duplicate_group_member", ["photo_id"])
    op.create_index("ix_job_item_job_status", "job_item", ["job_id", "status"])

    # FTS5 shadow tables (SDD §5.3/§7.3): one per source table rather than one
    # combined "metadata" table spanning `metadata` + `photo`.filename, since a
    # single-source trigger is far simpler to keep correct than a two-source
    # merge; TASK-052's query layer is the seam that presents them as one
    # searchable surface to callers.
    op.execute(
        "CREATE VIRTUAL TABLE ai_result_fts USING "
        "fts5(result_id UNINDEXED, photo_id UNINDEXED, capability UNINDEXED, payload)"
    )
    op.execute("CREATE VIRTUAL TABLE photo_fts USING fts5(photo_id UNINDEXED, relative_path)")
    op.execute(
        "CREATE VIRTUAL TABLE metadata_fts USING "
        "fts5(photo_id UNINDEXED, camera_make, camera_model, lens)"
    )

    # ai_result: only `is_current` rows are shadowed, matching §5.4's
    # append-and-flip versioning -- a version flipped to not-current drops
    # out of search immediately, within the same transaction.
    op.execute(
        """
        CREATE TRIGGER trg_ai_result_fts_ai AFTER INSERT ON ai_result WHEN NEW.is_current = 1
        BEGIN
            INSERT INTO ai_result_fts(result_id, photo_id, capability, payload)
            VALUES (NEW.id, NEW.photo_id, NEW.capability, NEW.payload);
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_ai_result_fts_au AFTER UPDATE ON ai_result
        BEGIN
            DELETE FROM ai_result_fts WHERE result_id = OLD.id;
            INSERT INTO ai_result_fts(result_id, photo_id, capability, payload)
            SELECT NEW.id, NEW.photo_id, NEW.capability, NEW.payload WHERE NEW.is_current = 1;
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_ai_result_fts_ad AFTER DELETE ON ai_result
        BEGIN
            DELETE FROM ai_result_fts WHERE result_id = OLD.id;
        END
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_photo_fts_ai AFTER INSERT ON photo
        BEGIN
            INSERT INTO photo_fts(photo_id, relative_path) VALUES (NEW.id, NEW.relative_path);
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_photo_fts_au AFTER UPDATE OF relative_path ON photo
        BEGIN
            DELETE FROM photo_fts WHERE photo_id = OLD.id;
            INSERT INTO photo_fts(photo_id, relative_path) VALUES (NEW.id, NEW.relative_path);
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_photo_fts_ad AFTER DELETE ON photo
        BEGIN
            DELETE FROM photo_fts WHERE photo_id = OLD.id;
        END
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_metadata_fts_ai AFTER INSERT ON metadata
        BEGIN
            INSERT INTO metadata_fts(photo_id, camera_make, camera_model, lens)
            VALUES (NEW.photo_id, NEW.camera_make, NEW.camera_model, NEW.lens);
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_metadata_fts_au AFTER UPDATE ON metadata
        BEGIN
            DELETE FROM metadata_fts WHERE photo_id = OLD.photo_id;
            INSERT INTO metadata_fts(photo_id, camera_make, camera_model, lens)
            VALUES (NEW.photo_id, NEW.camera_make, NEW.camera_model, NEW.lens);
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_metadata_fts_ad AFTER DELETE ON metadata
        BEGIN
            DELETE FROM metadata_fts WHERE photo_id = OLD.photo_id;
        END
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    for trigger in (
        "trg_metadata_fts_ad",
        "trg_metadata_fts_au",
        "trg_metadata_fts_ai",
        "trg_photo_fts_ad",
        "trg_photo_fts_au",
        "trg_photo_fts_ai",
        "trg_ai_result_fts_ad",
        "trg_ai_result_fts_au",
        "trg_ai_result_fts_ai",
    ):
        op.execute(f"DROP TRIGGER {trigger}")

    for table in ("metadata_fts", "photo_fts", "ai_result_fts"):
        op.execute(f"DROP TABLE {table}")

    op.drop_index("ix_job_item_job_status", table_name="job_item")
    op.drop_index("ix_duplicate_group_member_photo_id", table_name="duplicate_group_member")
    with op.batch_alter_table("embedding_ref") as batch_op:
        batch_op.drop_constraint("uq_embedding_ref_photo_vector_space", type_="unique")
    op.drop_index("ix_ai_result_plugin_model_version", table_name="ai_result")
    op.drop_index("ix_ai_result_photo_capability_current", table_name="ai_result")
    op.drop_index("ix_photo_captured_at_local", table_name="photo")
