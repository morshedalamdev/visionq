"""Add controlled local image upload requests without automatic inference."""

from alembic import op

revision = "0007_upload_requests"
down_revision = "0006_mcp_evidence"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE image_upload_requests (
            id uuid PRIMARY KEY,
            original_filename text NOT NULL
                CHECK (length(original_filename) BETWEEN 1 AND 255),
            content_sha256 catalog_sha256 NOT NULL UNIQUE,
            byte_count bigint NOT NULL
                CHECK (byte_count > 0 AND byte_count <= 20000000),
            media_type text NOT NULL
                CHECK (media_type IN ('image/png', 'image/jpeg')),
            width integer NOT NULL CHECK (width > 0),
            height integer NOT NULL CHECK (height > 0),
            pixel_count bigint NOT NULL GENERATED ALWAYS AS (
                width::bigint * height::bigint
            ) STORED CHECK (pixel_count <= 10000000),
            artifact_uri text NOT NULL
                CHECK (artifact_uri = 'uploads/objects/' || content_sha256::text),
            dataset_version_id uuid REFERENCES dataset_versions(id),
            batch_id uuid,
            status text NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'ready', 'failed')),
            inference_state text NOT NULL DEFAULT 'not_started'
                CHECK (inference_state IN (
                    'not_started', 'pending_registration', 'unavailable'
                )),
            failure_reason text,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (id, content_sha256),
            FOREIGN KEY (batch_id, dataset_version_id)
                REFERENCES batches(id, dataset_version_id),
            CHECK (batch_id IS NULL OR dataset_version_id IS NOT NULL),
            CHECK (
                status <> 'failed' OR (failure_reason IS NOT NULL)
            ),
            CHECK (
                status <> 'pending' OR failure_reason IS NULL
            )
        )
    """)
    op.execute("""
        CREATE INDEX image_upload_requests_status_idx
        ON image_upload_requests(status, created_at DESC)
    """)


def downgrade():
    op.drop_table("image_upload_requests")
