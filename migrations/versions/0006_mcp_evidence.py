"""Extend immutable analytics evidence for multi-scope MCP use."""

from alembic import op

revision = "0006_mcp_evidence"
down_revision = "0005_retrieval"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE analytics_snapshots
        ADD COLUMN pinned_corpus_version_id uuid,
        ADD COLUMN pinned_retrieval_index_id uuid
    """)
    op.execute("""
        ALTER TABLE analytics_snapshots
        ADD CONSTRAINT analytics_snapshots_retrieval_pin_check
        CHECK (
            (pinned_corpus_version_id IS NULL)
            = (pinned_retrieval_index_id IS NULL)
        )
    """)
    op.execute("""
        ALTER TABLE analytics_snapshots
        ADD CONSTRAINT analytics_snapshots_retrieval_pin_fk
        FOREIGN KEY (pinned_retrieval_index_id, pinned_corpus_version_id)
        REFERENCES retrieval_indexes(id, corpus_version_id)
    """)
    op.execute("""
        CREATE INDEX analytics_snapshots_retrieval_idx
        ON analytics_snapshots (
            pinned_corpus_version_id, pinned_retrieval_index_id
        )
    """)


def downgrade():
    op.drop_index(
        "analytics_snapshots_retrieval_idx",
        table_name="analytics_snapshots",
    )
    op.drop_constraint(
        "analytics_snapshots_retrieval_pin_fk",
        "analytics_snapshots",
        type_="foreignkey",
    )
    op.drop_constraint(
        "analytics_snapshots_retrieval_pin_check",
        "analytics_snapshots",
        type_="check",
    )
    op.execute("""
        ALTER TABLE analytics_snapshots
        DROP COLUMN pinned_retrieval_index_id,
        DROP COLUMN pinned_corpus_version_id
    """)
