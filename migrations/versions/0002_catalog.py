"""Add immutable dataset catalog and ingestion progress."""

from alembic import op

revision = "0002_catalog"
down_revision = "0001_fixture"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE DOMAIN catalog_sha256 AS text
        CHECK (VALUE ~ '^[0-9a-f]{64}$')
    """)

    op.execute("""
        CREATE TABLE catalog_artifacts (
            sha256 catalog_sha256 PRIMARY KEY,
            byte_count bigint NOT NULL CHECK (byte_count >= 0),
            artifact_uri text GENERATED ALWAYS AS
                ('catalog/objects/' || sha256::text) STORED,
            UNIQUE (artifact_uri)
        )
    """)

    op.execute("""
        CREATE TABLE dataset_versions (
            id uuid PRIMARY KEY,
            dataset_name text NOT NULL CHECK (btrim(dataset_name) <> ''),
            version integer NOT NULL CHECK (version > 0),
            evidence_kind text NOT NULL
                CHECK (evidence_kind IN ('synthetic', 'released')),
            source_identity_kind text NOT NULL
                CHECK (source_identity_kind IN
                    ('archive_sha256', 'extracted_manifest_sha256')),
            source_identity catalog_sha256 NOT NULL,
            source_manifest_sha256 catalog_sha256 NOT NULL
                REFERENCES catalog_artifacts(sha256),
            release_manifest_sha256 catalog_sha256 NOT NULL
                REFERENCES catalog_artifacts(sha256),
            importer_config_sha256 catalog_sha256 NOT NULL,
            class_map_version text NOT NULL
                CHECK (class_map_version = 'neu-det-v1'),
            archive_sha256 catalog_sha256,
            acquisition_url text,
            acquired_at timestamptz,
            redistribution_terms text,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (dataset_name, version),
            UNIQUE (
                dataset_name, source_identity_kind, source_identity,
                release_manifest_sha256, importer_config_sha256
            ),
            CHECK (
                (source_identity_kind = 'archive_sha256'
                 AND archive_sha256 IS NOT NULL
                 AND source_identity = archive_sha256)
                OR
                (source_identity_kind = 'extracted_manifest_sha256'
                 AND source_identity = source_manifest_sha256)
            )
        )
    """)

    op.execute("""
        CREATE TABLE assets (
            id uuid PRIMARY KEY,
            raw_sha256 catalog_sha256 NOT NULL UNIQUE
                REFERENCES catalog_artifacts(sha256),
            pixel_sha256 catalog_sha256 NOT NULL,
            width integer NOT NULL CHECK (width > 0),
            height integer NOT NULL CHECK (height > 0),
            channels integer NOT NULL CHECK (channels IN (1, 3)),
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE annotation_revisions (
            dataset_version_id uuid NOT NULL REFERENCES dataset_versions(id),
            asset_id uuid NOT NULL REFERENCES assets(id),
            revision_sha256 catalog_sha256 NOT NULL,
            source_xml_sha256 catalog_sha256 NOT NULL
                REFERENCES catalog_artifacts(sha256),
            parent_revision_sha256 catalog_sha256,
            lineage jsonb NOT NULL CHECK (jsonb_typeof(lineage) = 'object'),
            PRIMARY KEY (dataset_version_id, asset_id, revision_sha256),
            FOREIGN KEY (
                dataset_version_id, asset_id, parent_revision_sha256
            ) REFERENCES annotation_revisions (
                dataset_version_id, asset_id, revision_sha256
            ),
            CHECK (
                parent_revision_sha256 IS NULL
                OR parent_revision_sha256 <> revision_sha256
            )
        )
    """)

    op.execute("""
        CREATE TABLE annotations (
            dataset_version_id uuid NOT NULL,
            asset_id uuid NOT NULL,
            revision_sha256 catalog_sha256 NOT NULL,
            ordinal integer NOT NULL CHECK (ordinal >= 0),
            class_id integer NOT NULL CHECK (class_id BETWEEN 0 AND 5),
            box_xmin double precision NOT NULL,
            box_ymin double precision NOT NULL,
            box_xmax double precision NOT NULL,
            box_ymax double precision NOT NULL,
            PRIMARY KEY (
                dataset_version_id, asset_id, revision_sha256, ordinal
            ),
            FOREIGN KEY (
                dataset_version_id, asset_id, revision_sha256
            ) REFERENCES annotation_revisions (
                dataset_version_id, asset_id, revision_sha256
            ),
            CHECK (
                0 <= box_xmin AND box_xmin < box_xmax
                AND box_xmax < 'Infinity'::double precision
                AND 0 <= box_ymin AND box_ymin < box_ymax
                AND box_ymax < 'Infinity'::double precision
            )
        )
    """)

    op.execute("""
        CREATE TABLE dataset_groups (
            dataset_version_id uuid NOT NULL REFERENCES dataset_versions(id),
            group_id catalog_sha256 NOT NULL,
            split text NOT NULL CHECK (split IN ('train', 'validation', 'test')),
            PRIMARY KEY (dataset_version_id, group_id),
            UNIQUE (dataset_version_id, group_id, split)
        )
    """)

    op.execute("""
        CREATE TABLE dataset_items (
            dataset_version_id uuid NOT NULL,
            asset_id uuid NOT NULL,
            group_id catalog_sha256 NOT NULL,
            split text NOT NULL,
            revision_sha256 catalog_sha256 NOT NULL,
            PRIMARY KEY (dataset_version_id, asset_id),
            FOREIGN KEY (dataset_version_id, group_id, split)
                REFERENCES dataset_groups(dataset_version_id, group_id, split),
            FOREIGN KEY (dataset_version_id, asset_id, revision_sha256)
                REFERENCES annotation_revisions(
                    dataset_version_id, asset_id, revision_sha256
                )
        )
    """)

    op.execute("""
        CREATE TABLE quality_issues (
            id uuid PRIMARY KEY,
            dataset_version_id uuid NOT NULL REFERENCES dataset_versions(id),
            asset_id uuid REFERENCES assets(id),
            rule_id text NOT NULL CHECK (btrim(rule_id) <> ''),
            severity text NOT NULL CHECK (severity IN ('warning', 'error')),
            details jsonb NOT NULL CHECK (jsonb_typeof(details) = 'object')
        )
    """)

    op.execute("""
        CREATE TABLE ingestion_runs (
            id uuid PRIMARY KEY,
            dataset_version_id uuid NOT NULL UNIQUE
                REFERENCES dataset_versions(id),
            status text NOT NULL DEFAULT 'pending'
                CHECK (status IN
                    ('pending', 'running', 'succeeded', 'partial', 'failed')),
            expected_items integer NOT NULL CHECK (expected_items >= 0),
            started_at timestamptz,
            finished_at timestamptz,
            last_error text,
            UNIQUE (id, dataset_version_id),
            CHECK (status = 'pending' OR started_at IS NOT NULL),
            CHECK (
                (status IN ('succeeded', 'partial', 'failed'))
                = (finished_at IS NOT NULL)
            )
        )
    """)

    op.execute("""
        CREATE TABLE ingestion_items (
            run_id uuid NOT NULL,
            dataset_version_id uuid NOT NULL,
            asset_id uuid NOT NULL,
            expected_raw_sha256 catalog_sha256 NOT NULL,
            status text NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'running', 'succeeded', 'failed')),
            attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
            catalog_asset_id uuid,
            last_error text,
            PRIMARY KEY (run_id, asset_id),
            FOREIGN KEY (run_id, dataset_version_id)
                REFERENCES ingestion_runs(id, dataset_version_id),
            FOREIGN KEY (dataset_version_id, catalog_asset_id)
                REFERENCES dataset_items(dataset_version_id, asset_id),
            CHECK (
                (status = 'succeeded') = (catalog_asset_id IS NOT NULL)
            ),
            CHECK (
                catalog_asset_id IS NULL OR catalog_asset_id = asset_id
            )
        )
    """)

    op.execute("""
        CREATE INDEX dataset_items_split_idx
        ON dataset_items(dataset_version_id, split)
    """)
    op.execute("""
        CREATE INDEX ingestion_items_status_idx
        ON ingestion_items(run_id, status)
    """)

    op.execute("""
        CREATE FUNCTION catalog_check_box() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE
            image_width integer;
            image_height integer;
        BEGIN
            SELECT width, height
            INTO image_width, image_height
            FROM assets
            WHERE id = NEW.asset_id;

            IF NOT FOUND THEN
                RAISE EXCEPTION 'annotation asset is missing'
                    USING ERRCODE = '23503';
            END IF;

            IF NEW.box_xmax > image_width
               OR NEW.box_ymax > image_height THEN
                RAISE EXCEPTION 'annotation exceeds asset dimensions'
                    USING ERRCODE = '23514';
            END IF;

            RETURN NEW;
        END
        $$
    """)

    op.execute("""
        CREATE TRIGGER annotations_bounds
        BEFORE INSERT ON annotations
        FOR EACH ROW EXECUTE FUNCTION catalog_check_box()
    """)

    op.execute("""
        CREATE FUNCTION catalog_reject_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'catalog identities are immutable'
                USING ERRCODE = '23514';
        END
        $$
    """)

    for table in (
        "catalog_artifacts",
        "dataset_versions",
        "assets",
        "annotation_revisions",
        "annotations",
        "dataset_groups",
        "dataset_items",
        "quality_issues",
    ):
        op.execute(f"""
            CREATE TRIGGER {table}_immutable
            BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION catalog_reject_mutation()
            """)


def downgrade():
    for table in (
        "ingestion_items",
        "ingestion_runs",
        "quality_issues",
        "dataset_items",
        "dataset_groups",
        "annotations",
        "annotation_revisions",
        "assets",
        "dataset_versions",
        "catalog_artifacts",
    ):
        op.drop_table(table)

    op.execute("DROP FUNCTION catalog_check_box()")
    op.execute("DROP FUNCTION catalog_reject_mutation()")
    op.execute("DROP DOMAIN catalog_sha256")
