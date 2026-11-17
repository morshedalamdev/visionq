"""Introduce the versioned inspection fixture."""

from alembic import op

revision = "0001_fixture"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("""
CREATE TABLE inspection_fixture (
inspection_id uuid NOT NULL,
version integer NOT NULL CHECK (version > 0),
sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
artifact_uri text NOT NULL,
byte_count bigint NOT NULL CHECK (byte_count >= 0),
created_at timestamptz NOT NULL DEFAULT now(),
PRIMARY KEY (inspection_id, version),
CHECK (artifact_uri = 'object/' || sha256 || '.pgm')
)
""")


def downgrade():
    op.drop_table("inspection_fixture")
