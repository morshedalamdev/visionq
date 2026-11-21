"""Add immutable batch inference lineage and resumable prediction state."""

from alembic import op

revision = "0003_inference"
down_revision = "0002_catalog"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE models (
            id uuid PRIMARY KEY,
            dataset_version_id uuid NOT NULL REFERENCES dataset_versions(id),
            evidence_kind text NOT NULL
                CHECK (evidence_kind IN ('synthetic', 'released')),
            architecture text NOT NULL CHECK (btrim(architecture) <> ''),
            class_map_version text NOT NULL
                CHECK (class_map_version = 'neu-det-v1'),
            classes jsonb NOT NULL CHECK (jsonb_typeof(classes) = 'array'),
            checkpoint_sha256 catalog_sha256 NOT NULL
                REFERENCES catalog_artifacts(sha256),
            checkpoint_bytes bigint NOT NULL CHECK (checkpoint_bytes > 0),
            training_manifest_sha256 catalog_sha256 NOT NULL,
            selection_manifest_sha256 catalog_sha256 NOT NULL,
            inference_config_sha256 catalog_sha256 NOT NULL,
            inference_config jsonb NOT NULL
                CHECK (jsonb_typeof(inference_config) = 'object'),
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (id, dataset_version_id)
        )
    """)

    op.execute("""
        CREATE TABLE batches (
            id uuid PRIMARY KEY,
            dataset_version_id uuid NOT NULL REFERENCES dataset_versions(id),
            kind text NOT NULL CHECK (btrim(kind) <> ''),
            split text CHECK (
                split IS NULL OR split IN ('train', 'validation', 'test')
            ),
            membership_sha256 catalog_sha256 NOT NULL,
            member_count integer NOT NULL CHECK (member_count > 0),
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (dataset_version_id, membership_sha256),
            UNIQUE (id, dataset_version_id)
        )
    """)

    op.execute("""
        CREATE TABLE batch_items (
            batch_id uuid NOT NULL,
            dataset_version_id uuid NOT NULL,
            asset_id uuid NOT NULL,
            ordinal integer NOT NULL CHECK (ordinal >= 0),
            image_sha256 catalog_sha256 NOT NULL
                REFERENCES catalog_artifacts(sha256),
            PRIMARY KEY (batch_id, asset_id),
            UNIQUE (batch_id, ordinal),
            UNIQUE (batch_id, dataset_version_id, asset_id),
            FOREIGN KEY (batch_id, dataset_version_id)
                REFERENCES batches(id, dataset_version_id),
            FOREIGN KEY (dataset_version_id, asset_id)
                REFERENCES dataset_items(dataset_version_id, asset_id)
        )
    """)

    op.execute("""
        CREATE TABLE inference_runs (
            id uuid PRIMARY KEY,
            dataset_version_id uuid NOT NULL,
            batch_id uuid NOT NULL,
            model_id uuid NOT NULL,
            status text NOT NULL DEFAULT 'pending'
                CHECK (status IN
                    ('pending', 'running', 'succeeded', 'partial', 'failed')),
            config_sha256 catalog_sha256 NOT NULL,
            config jsonb NOT NULL CHECK (jsonb_typeof(config) = 'object'),
            expected_items integer NOT NULL CHECK (expected_items > 0),
            started_at timestamptz,
            finished_at timestamptz,
            last_error text,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (id, dataset_version_id, batch_id),
            UNIQUE (dataset_version_id, batch_id, model_id, config_sha256),
            FOREIGN KEY (batch_id, dataset_version_id)
                REFERENCES batches(id, dataset_version_id),
            FOREIGN KEY (model_id, dataset_version_id)
                REFERENCES models(id, dataset_version_id),
            CHECK (status = 'pending' OR started_at IS NOT NULL),
            CHECK (
                (status IN ('succeeded', 'partial', 'failed'))
                = (finished_at IS NOT NULL)
            )
        )
    """)

    op.execute("""
        CREATE TABLE image_results (
            run_id uuid NOT NULL,
            dataset_version_id uuid NOT NULL,
            batch_id uuid NOT NULL,
            asset_id uuid NOT NULL,
            status text NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'running', 'succeeded', 'failed')),
            attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0 AND attempts <= 3),
            image_sha256 catalog_sha256 NOT NULL,
            raw_prediction_count integer
                CHECK (raw_prediction_count IS NULL OR raw_prediction_count >= 0),
            detection_count integer
                CHECK (detection_count IS NULL OR detection_count >= 0),
            prediction_sha256 catalog_sha256,
            latency_ms double precision
                CHECK (latency_ms IS NULL OR latency_ms >= 0),
            last_error text,
            started_at timestamptz,
            finished_at timestamptz,
            PRIMARY KEY (run_id, asset_id),
            UNIQUE (run_id, asset_id, status),
            FOREIGN KEY (run_id, dataset_version_id, batch_id)
                REFERENCES inference_runs(id, dataset_version_id, batch_id),
            FOREIGN KEY (batch_id, dataset_version_id, asset_id)
                REFERENCES batch_items(batch_id, dataset_version_id, asset_id),
            CHECK (
                status <> 'succeeded'
                OR (
                    raw_prediction_count IS NOT NULL
                    AND detection_count IS NOT NULL
                    AND prediction_sha256 IS NOT NULL
                    AND latency_ms IS NOT NULL
                    AND finished_at IS NOT NULL
                    AND last_error IS NULL
                )
            ),
            CHECK (
                status <> 'failed' OR (finished_at IS NOT NULL AND last_error IS NOT NULL)
            )
        )
    """)

    op.execute("""
        CREATE TABLE detections (
            run_id uuid NOT NULL,
            asset_id uuid NOT NULL,
            status text NOT NULL DEFAULT 'succeeded'
                CHECK (status = 'succeeded'),
            ordinal integer NOT NULL CHECK (ordinal >= 0),
            class_id integer NOT NULL CHECK (class_id BETWEEN 0 AND 5),
            confidence double precision NOT NULL
                CHECK (confidence BETWEEN 0 AND 1),
            box_xmin double precision NOT NULL,
            box_ymin double precision NOT NULL,
            box_xmax double precision NOT NULL,
            box_ymax double precision NOT NULL,
            PRIMARY KEY (run_id, asset_id, ordinal),
            FOREIGN KEY (run_id, asset_id, status)
                REFERENCES image_results(run_id, asset_id, status),
            CHECK (
                box_xmin >= 0 AND box_ymin >= 0
                AND box_xmin < box_xmax AND box_ymin < box_ymax
                AND box_xmax < 'Infinity'::double precision
                AND box_ymax < 'Infinity'::double precision
            )
        )
    """)

    op.execute("""
        CREATE TABLE image_overlays (
            run_id uuid NOT NULL,
            asset_id uuid NOT NULL,
            renderer_version text NOT NULL CHECK (btrim(renderer_version) <> ''),
            overlay_sha256 catalog_sha256 NOT NULL
                REFERENCES catalog_artifacts(sha256),
            overlay_bytes bigint NOT NULL CHECK (overlay_bytes > 0),
            source_image_sha256 catalog_sha256 NOT NULL,
            detection_count integer NOT NULL CHECK (detection_count >= 0),
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (run_id, asset_id),
            FOREIGN KEY (run_id, asset_id)
                REFERENCES image_results(run_id, asset_id),
            UNIQUE (run_id, asset_id, source_image_sha256, detection_count)
        )
    """)

    op.execute("""
        CREATE INDEX inference_runs_status_idx ON inference_runs(status)
    """)
    op.execute("""
        CREATE INDEX image_results_status_idx ON image_results(run_id, status)
    """)
    op.execute("""
        CREATE INDEX detections_class_idx
        ON detections(run_id, class_id)
    """)

    op.execute("""
        CREATE FUNCTION inference_check_box() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE
            image_width integer;
            image_height integer;
        BEGIN
            SELECT assets.width, assets.height
            INTO image_width, image_height
            FROM assets
            WHERE assets.id = NEW.asset_id;

            IF NOT FOUND THEN
                RAISE EXCEPTION 'detection asset is missing'
                    USING ERRCODE = '23503';
            END IF;

            IF NEW.box_xmax > image_width OR NEW.box_ymax > image_height THEN
                RAISE EXCEPTION 'detection exceeds asset dimensions'
                    USING ERRCODE = '23514';
            END IF;

            RETURN NEW;
        END
        $$
    """)
    op.execute("""
        CREATE TRIGGER detections_bounds
        BEFORE INSERT ON detections
        FOR EACH ROW EXECUTE FUNCTION inference_check_box()
    """)

    op.execute("""
        CREATE FUNCTION inference_guard_run_lineage() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF ROW(
                NEW.id, NEW.dataset_version_id, NEW.batch_id, NEW.model_id,
                NEW.config_sha256, NEW.config, NEW.expected_items
            ) IS DISTINCT FROM ROW(
                OLD.id, OLD.dataset_version_id, OLD.batch_id, OLD.model_id,
                OLD.config_sha256, OLD.config, OLD.expected_items
            ) THEN
                RAISE EXCEPTION 'inference run lineage is immutable'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END
        $$
    """)
    op.execute("""
        CREATE TRIGGER inference_runs_lineage_immutable
        BEFORE UPDATE ON inference_runs
        FOR EACH ROW EXECUTE FUNCTION inference_guard_run_lineage()
    """)

    op.execute("""
        CREATE FUNCTION inference_guard_result() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF OLD.status = 'succeeded' THEN
                RAISE EXCEPTION 'successful inference results are immutable'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END
        $$
    """)
    op.execute("""
        CREATE TRIGGER image_results_success_immutable
        BEFORE UPDATE ON image_results
        FOR EACH ROW EXECUTE FUNCTION inference_guard_result()
    """)
    op.execute("""
        CREATE TRIGGER inference_runs_delete_immutable
        BEFORE DELETE ON inference_runs
        FOR EACH ROW EXECUTE FUNCTION catalog_reject_mutation()
    """)
    op.execute("""
        CREATE TRIGGER image_results_delete_immutable
        BEFORE DELETE ON image_results
        FOR EACH ROW EXECUTE FUNCTION catalog_reject_mutation()
    """)

    for table in (
        "models",
        "batches",
        "batch_items",
        "detections",
        "image_overlays",
    ):
        op.execute(f"""
            CREATE TRIGGER {table}_immutable
            BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION catalog_reject_mutation()
        """)


def downgrade():
    for table in (
        "image_overlays",
        "detections",
        "image_results",
        "inference_runs",
        "batch_items",
        "batches",
        "models",
    ):
        op.drop_table(table)
    op.execute("DROP FUNCTION inference_check_box()")
    op.execute("DROP FUNCTION inference_guard_run_lineage()")
    op.execute("DROP FUNCTION inference_guard_result()")
