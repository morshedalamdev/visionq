"""Add immutable API-owned analytics snapshot evidence."""

from alembic import op

revision = "0004_analytics"
down_revision = "0003_inference"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE analytics_snapshots (
            id uuid PRIMARY KEY,
            dataset_version_id uuid NOT NULL,
            batch_id uuid NOT NULL,
            inference_run_id uuid NOT NULL,
            metric_catalog_version text NOT NULL
                CHECK (btrim(metric_catalog_version) <> ''),
            run_status text NOT NULL CHECK (
                run_status IN ('pending', 'running', 'succeeded', 'partial', 'failed')
            ),
            evidence_status text NOT NULL CHECK (
                evidence_status IN (
                    'available', 'pending', 'partial', 'failed', 'unavailable'
                )
            ),
            payload_sha256 catalog_sha256 NOT NULL UNIQUE,
            payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
            captured_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (id, dataset_version_id, batch_id, inference_run_id),
            FOREIGN KEY (
                inference_run_id, dataset_version_id, batch_id
            ) REFERENCES inference_runs (
                id, dataset_version_id, batch_id
            )
        )
    """)
    op.execute("""
        CREATE INDEX analytics_snapshots_scope_idx
        ON analytics_snapshots (
            dataset_version_id, batch_id, inference_run_id, captured_at
        )
    """)
    op.execute("""
        CREATE FUNCTION analytics_snapshot_reject_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'analytics snapshots are immutable'
                USING ERRCODE = '23514';
        END
        $$
    """)
    op.execute("""
        CREATE TRIGGER analytics_snapshots_immutable
        BEFORE UPDATE OR DELETE ON analytics_snapshots
        FOR EACH ROW EXECUTE FUNCTION analytics_snapshot_reject_mutation()
    """)


def downgrade():
    op.drop_table("analytics_snapshots")
    op.execute("DROP FUNCTION analytics_snapshot_reject_mutation()")
