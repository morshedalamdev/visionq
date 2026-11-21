"""PostgreSQL constraints for M3.T3 inference identities and geometry."""

from uuid import UUID

import pytest
from catalog_support import build_release
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from worker.catalog import ingest
from worker.inference import (
    register_batch,
    register_model_contract,
    run_inference,
)
from worker.validation import CLASSES, sha256


def registered(postgres_engine, tmp_path):
    package, _ = build_release(tmp_path, "synthetic-m3t3-schema", 1)
    artifact_root = tmp_path / "artifacts"
    ingest(postgres_engine, artifact_root, package)
    batch = register_batch(
        postgres_engine,
        artifact_root,
        package.version_id,
        "test",
    )
    checkpoint = tmp_path / "checkpoint.pt"
    checkpoint.write_bytes(b"synthetic-checkpoint")
    model = register_model_contract(
        postgres_engine,
        artifact_root,
        package.version_id,
        {
            "checkpoint_path": checkpoint,
            "checkpoint_sha256": sha256(checkpoint.read_bytes()),
            "checkpoint_bytes": checkpoint.stat().st_size,
            "training_manifest_sha256": "b" * 64,
            "selection_manifest_sha256": "c" * 64,
            "dataset_manifest_sha256": package.rows["dataset_versions"][0][
                "release_manifest_sha256"
            ],
            "classes": list(CLASSES),
            "evidence_kind": "synthetic",
            "inference_config": {
                "tool_version": "m3t3-v1",
                "checkpoint": "best",
                "predictor": "synthetic",
                "settings": {"imgsz": 320, "conf": 0.001},
                "confidence_threshold": 0.07,
                "match_iou": 0.5,
            },
        },
    )
    return artifact_root, batch, model


def test_inference_migration_and_immutable_checkpoint(postgres_engine, tmp_path):
    artifact_root, batch, model = registered(postgres_engine, tmp_path)
    assert batch["member_count"] > 0
    assert UUID(model["id"])

    with postgres_engine.connect() as connection:
        with pytest.raises(IntegrityError), connection.begin_nested():
            connection.execute(
                text(
                    "UPDATE models SET checkpoint_bytes = checkpoint_bytes + 1 "
                    "WHERE id = CAST(:id AS uuid)"
                ),
                {"id": model["id"]},
            )
        assert (
            connection.scalar(
                text(
                    "SELECT checkpoint_bytes FROM models WHERE id = CAST(:id AS uuid)"
                ),
                {"id": model["id"]},
            )
            == (artifact_root / "catalog/objects" / model["checkpoint_sha256"])
            .stat()
            .st_size
        )


def test_success_rows_and_detections_are_immutable(postgres_engine, tmp_path):
    artifact_root, batch, model = registered(postgres_engine, tmp_path)
    run = run_inference(
        postgres_engine,
        artifact_root,
        batch["batch_id"],
        model["id"],
        "cpu",
        predictor=lambda path, settings, device: [
            {"cls": 1, "conf": 0.8, "box": [0, 0, 10, 10]}
        ],
    )
    run_id = run["run_id"]

    with postgres_engine.connect() as connection:
        asset_id = connection.scalar(
            text(
                "SELECT asset_id FROM image_results "
                "WHERE run_id = CAST(:run AS uuid) ORDER BY asset_id LIMIT 1"
            ),
            {"run": run_id},
        )
        parameters = {"run": run_id, "asset": asset_id}
        with pytest.raises(IntegrityError), connection.begin_nested():
            connection.execute(
                text(
                    "UPDATE image_results SET status = 'failed' "
                    "WHERE run_id = CAST(:run AS uuid) "
                    "AND asset_id = CAST(:asset AS uuid)"
                ),
                parameters,
            )
        with pytest.raises(IntegrityError), connection.begin_nested():
            connection.execute(
                text(
                    "UPDATE detections SET confidence = 0.7 "
                    "WHERE run_id = CAST(:run AS uuid) "
                    "AND asset_id = CAST(:asset AS uuid)"
                ),
                parameters,
            )
        with pytest.raises(IntegrityError), connection.begin_nested():
            connection.execute(
                text(
                    "DELETE FROM image_results "
                    "WHERE run_id = CAST(:run AS uuid) "
                    "AND asset_id = CAST(:asset AS uuid)"
                ),
                parameters,
            )
        with pytest.raises(IntegrityError), connection.begin_nested():
            connection.execute(
                text("DELETE FROM inference_runs WHERE id = CAST(:run AS uuid)"),
                parameters,
            )


def test_detection_geometry_and_confidence_constraints(postgres_engine, tmp_path):
    artifact_root, batch, model = registered(postgres_engine, tmp_path)
    run = run_inference(
        postgres_engine,
        artifact_root,
        batch["batch_id"],
        model["id"],
        "cpu",
        predictor=lambda path, settings, device: [],
    )
    with postgres_engine.connect() as connection:
        asset_id, width, height = connection.execute(
            text("""
                SELECT ir.asset_id, a.width, a.height
                FROM image_results AS ir
                JOIN assets AS a ON a.id = ir.asset_id
                WHERE ir.run_id = CAST(:run AS uuid)
                ORDER BY ir.asset_id
                LIMIT 1
            """),
            {"run": run["run_id"]},
        ).one()
        parameters = {
            "run": run["run_id"],
            "asset": asset_id,
            "confidence": 1.01,
            "xmax": width + 1,
            "ymax": height + 1,
        }
        with pytest.raises(IntegrityError), connection.begin_nested():
            connection.execute(
                text("""
                    INSERT INTO detections (
                        run_id, asset_id, status, ordinal, class_id, confidence,
                        box_xmin, box_ymin, box_xmax, box_ymax
                    ) VALUES (
                        CAST(:run AS uuid), CAST(:asset AS uuid), 'succeeded',
                        99, 0, :confidence, 0, 0, :xmax, :ymax
                    )
                """),
                parameters,
            )
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM detections WHERE run_id = CAST(:run AS uuid)"
                ),
                {"run": run["run_id"]},
            )
            == 0
        )
