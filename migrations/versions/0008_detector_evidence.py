"""Immutable verified detector research evidence, separate from predictions."""

from alembic import op

revision = "0008_detector_evidence"
down_revision = "0007_upload_requests"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE detector_evidence (
            sha256 catalog_sha256 PRIMARY KEY,
            kind text NOT NULL CHECK (kind IN ('evaluation', 'performance')),
            dataset_version_id uuid NOT NULL,
            model_id uuid NOT NULL,
            evaluation_sha256 catalog_sha256 REFERENCES detector_evidence(sha256),
            payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
            manifest_bytes bytea NOT NULL,
            registered_at timestamptz NOT NULL DEFAULT now(),
            FOREIGN KEY (model_id, dataset_version_id)
                REFERENCES models(id, dataset_version_id),
            CHECK ((kind = 'evaluation' AND evaluation_sha256 IS NULL) OR
                   (kind = 'performance' AND evaluation_sha256 IS NOT NULL))
        );
        CREATE UNIQUE INDEX detector_one_evaluation_per_model
            ON detector_evidence(model_id) WHERE kind = 'evaluation';
        CREATE TRIGGER detector_evidence_immutable
            BEFORE UPDATE OR DELETE ON detector_evidence
            FOR EACH ROW EXECUTE FUNCTION catalog_reject_mutation();
    """)


def downgrade():
    op.drop_table("detector_evidence")
