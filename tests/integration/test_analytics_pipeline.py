"""M4.T1 PostgreSQL analytics, comparison and snapshot evidence."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from catalog_support import build_release
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from analytics.metrics import AnalyticsScope
from analytics.service import (
    AnalyticsCompatibilityError,
    capture_snapshot,
    compare_scopes,
    read_snapshot,
)
from worker.catalog import ingest
from worker.inference import (
    register_batch,
    register_model_contract,
    run_inference,
)
from worker.validation import CLASSES, sha256


def setup_scope(postgres_engine, tmp_path: Path, name: str):
    package, _ = build_release(tmp_path / name, f"synthetic-{name}", 1)
    root = tmp_path / "artifacts"
    ingest(postgres_engine, root, package)
    batch = register_batch(
        postgres_engine,
        root,
        package.version_id,
        "test",
    )
    checkpoint = tmp_path / f"{name}.pt"
    checkpoint.write_bytes(f"analytics-{name}".encode())
    model = register_model_contract(
        postgres_engine,
        root,
        package.version_id,
        {
            "checkpoint_path": checkpoint,
            "checkpoint_sha256": sha256(checkpoint.read_bytes()),
            "checkpoint_bytes": checkpoint.stat().st_size,
            "training_manifest_sha256": "a" * 64,
            "selection_manifest_sha256": "b" * 64,
            "dataset_manifest_sha256": package.rows["dataset_versions"][0][
                "release_manifest_sha256"
            ],
            "classes": list(CLASSES),
            "evidence_kind": "synthetic",
            "inference_config": {
                "tool_version": "m3t3-v1",
                "checkpoint": "best",
                "predictor": "synthetic",
                "settings": {
                    "imgsz": 320,
                    "conf": 0.001,
                    "iou": 0.7,
                    "max_det": 300,
                },
                "confidence_threshold": 0.07,
                "match_iou": 0.5,
            },
        },
    )
    return {
        "engine": postgres_engine,
        "root": root,
        "package": package,
        "batch": batch,
        "model": model,
    }


def analytics_scope(fixture, run_id, class_id=None):
    return AnalyticsScope.from_values(
        fixture["batch"]["dataset_version_id"],
        fixture["batch"]["batch_id"],
        run_id,
        class_id,
    )


def execute_run(fixture, device, predictor, **kwargs):
    return run_inference(
        fixture["engine"],
        fixture["root"],
        fixture["batch"]["batch_id"],
        fixture["model"]["id"],
        device,
        predictor=predictor,
        **kwargs,
    )


def metric_map(snapshot):
    return {item["metric_name"]: item for item in snapshot["payload"]["metrics"]}


def box_predictor(path, settings, device):
    return [
        {"cls": 1, "conf": 0.9, "box": [0, 0, 4, 4]},
        {"cls": 3, "conf": 0.8, "box": [4, 4, 8, 8]},
    ]


def test_hand_calculated_metrics_class_filter_and_idempotent_rerun(
    postgres_engine, tmp_path
):
    fixture = setup_scope(postgres_engine, tmp_path, "counts")
    run = execute_run(fixture, "cpu", box_predictor)
    scope = analytics_scope(fixture, run["run_id"])
    snapshot = capture_snapshot(postgres_engine, scope)
    metrics = metric_map(snapshot)
    members = fixture["batch"]["member_count"]

    assert run["ok"] is True
    assert metrics["batch_image_count"]["value"] == members
    assert metrics["processed_image_count"]["value"] == members
    assert metrics["failed_image_count"]["value"] == 0
    assert metrics["pending_image_count"]["value"] == 0
    assert metrics["predicted_box_count"]["value"] == 2 * members
    assert metrics["images_with_prediction"]["value"] == members
    assert metrics["prediction_image_ratio"]["value"] == 1
    assert metrics["boxes_per_processed_image"]["value"] == 2
    assert metrics["processing_coverage"]["value"] == 1

    class_snapshot = capture_snapshot(
        postgres_engine,
        analytics_scope(fixture, run["run_id"], class_id=1),
    )
    class_metrics = metric_map(class_snapshot)
    assert class_metrics["predicted_box_count"]["value"] == members
    assert class_metrics["images_with_prediction"]["value"] == members

    repeated = execute_run(fixture, "cpu", box_predictor)
    assert repeated == run
    with postgres_engine.connect() as connection:
        detections = connection.scalar(
            text("""
                SELECT count(*)
                FROM detections
                WHERE run_id = CAST(:run AS uuid)
            """),
            {"run": run["run_id"]},
        )
    assert detections == 2 * members


def test_partial_and_failed_runs_preserve_unavailable_evidence(
    postgres_engine, tmp_path
):
    partial = setup_scope(postgres_engine, tmp_path, "partial")

    def interrupt(stage, asset_id):
        if stage == "after_item_commit":
            raise RuntimeError("test interruption")

    with pytest.raises(RuntimeError, match="interruption"):
        execute_run(partial, "cpu", lambda *args: [], hook=interrupt)
    with postgres_engine.connect() as connection:
        partial_run = connection.scalar(
            text("""
                SELECT id
                FROM inference_runs
                WHERE batch_id = CAST(:batch AS uuid)
            """),
            {"batch": partial["batch"]["batch_id"]},
        )

    partial_snapshot = capture_snapshot(
        postgres_engine,
        analytics_scope(partial, partial_run),
    )
    partial_metrics = metric_map(partial_snapshot)
    assert partial_snapshot["run_status"] == "partial"
    assert partial_metrics["processed_image_count"]["value"] == 1
    assert partial_metrics["pending_image_count"]["value"] == (
        partial["batch"]["member_count"] - 1
    )
    assert partial_metrics["prediction_image_ratio"]["value"] == 0
    assert partial_metrics["prediction_image_ratio"]["evidence_status"] == "partial"

    failed = setup_scope(postgres_engine, tmp_path, "failed")
    failed_run = execute_run(
        failed,
        "cpu",
        lambda *args: [{"cls": 0, "conf": 2, "box": [0, 0, 1, 1]}],
    )
    failed_snapshot = capture_snapshot(
        postgres_engine,
        analytics_scope(failed, failed_run["run_id"]),
    )
    failed_metrics = metric_map(failed_snapshot)
    assert failed_snapshot["run_status"] == "failed"
    assert (
        failed_metrics["failed_image_count"]["value"]
        == (failed["batch"]["member_count"])
    )
    assert failed_metrics["predicted_box_count"]["value"] is None
    assert failed_metrics["prediction_image_ratio"]["evidence_status"] == "unavailable"
    assert failed_metrics["prediction_image_ratio"]["reason"] == "no_successful_images"


def test_pair_comparison_handles_zero_baseline_and_class_scope(
    postgres_engine, tmp_path
):
    fixture = setup_scope(postgres_engine, tmp_path, "compare")
    left = execute_run(fixture, "cpu", lambda *args: [])
    right = execute_run(fixture, "mps", box_predictor)
    result = compare_scopes(
        postgres_engine,
        analytics_scope(fixture, left["run_id"], class_id=1),
        analytics_scope(fixture, right["run_id"], class_id=1),
        ["predicted_box_count", "prediction_image_ratio"],
    )
    metrics = {item["metric_name"]: item for item in result["metrics"]}

    assert (
        metrics["predicted_box_count"]["absolute_delta"]
        == (fixture["batch"]["member_count"])
    )
    assert metrics["predicted_box_count"]["relative_delta"] is None
    assert metrics["predicted_box_count"]["relative_delta_reason"] == "zero_left_value"
    assert metrics["prediction_image_ratio"]["absolute_delta"] == 1
    assert metrics["prediction_image_ratio"]["percentage_point_delta"] == 100

    with pytest.raises(AnalyticsCompatibilityError, match="class filters differ"):
        compare_scopes(
            postgres_engine,
            analytics_scope(fixture, left["run_id"]),
            analytics_scope(fixture, right["run_id"], class_id=1),
            ["predicted_box_count"],
        )


def test_shared_assets_are_isolated_between_dataset_versions(postgres_engine, tmp_path):
    first = setup_scope(postgres_engine, tmp_path, "version-one")
    second = setup_scope(postgres_engine, tmp_path, "version-two")
    first_run = execute_run(first, "cpu", box_predictor)
    second_run = execute_run(second, "cpu", lambda *args: [])

    first_snapshot = capture_snapshot(
        postgres_engine, analytics_scope(first, first_run["run_id"])
    )
    second_snapshot = capture_snapshot(
        postgres_engine, analytics_scope(second, second_run["run_id"])
    )
    first_metrics = metric_map(first_snapshot)
    second_metrics = metric_map(second_snapshot)

    assert first_snapshot["batch_id"] != second_snapshot["batch_id"]
    assert first_metrics["predicted_box_count"]["value"] == (
        2 * first["batch"]["member_count"]
    )
    assert second_metrics["predicted_box_count"]["value"] == 0
    with pytest.raises(AnalyticsCompatibilityError, match="dataset version differs"):
        compare_scopes(
            postgres_engine,
            analytics_scope(first, first_run["run_id"]),
            analytics_scope(second, second_run["run_id"]),
            ["batch_image_count"],
        )


def test_repeatable_read_snapshot_is_stable_under_concurrent_quality_insert(
    postgres_engine, tmp_path
):
    fixture = setup_scope(postgres_engine, tmp_path, "concurrent")
    run = execute_run(fixture, "cpu", lambda *args: [])
    scope = analytics_scope(fixture, run["run_id"])
    inserted = False

    def insert_quality(stage):
        nonlocal inserted
        if stage != "after_scope_read" or inserted:
            return
        with postgres_engine.begin() as writer:
            asset_id = writer.scalar(
                text("""
                    SELECT asset_id
                    FROM batch_items
                    WHERE batch_id = CAST(:batch AS uuid)
                    ORDER BY ordinal
                    LIMIT 1
                """),
                {"batch": fixture["batch"]["batch_id"]},
            )
            writer.execute(
                text("""
                    INSERT INTO quality_issues (
                        id, dataset_version_id, asset_id,
                        rule_id, severity, details
                    ) VALUES (
                        CAST(:id AS uuid),
                        CAST(:dataset AS uuid),
                        CAST(:asset AS uuid),
                        'concurrent-analytics-test',
                        'error',
                        CAST(:details AS jsonb)
                    )
                """),
                {
                    "id": str(uuid4()),
                    "dataset": fixture["batch"]["dataset_version_id"],
                    "asset": str(asset_id),
                    "details": '{"phase":"analytics"}',
                },
            )
        inserted = True

    snapshot = capture_snapshot(postgres_engine, scope, hook=insert_quality)
    before = metric_map(snapshot)["quality_issue_count"]["value"]
    with postgres_engine.connect() as connection:
        after = connection.scalar(
            text("""
                SELECT count(*)
                FROM quality_issues
                WHERE dataset_version_id = CAST(:dataset AS uuid)
            """),
            {"dataset": fixture["batch"]["dataset_version_id"]},
        )
    assert inserted is True
    assert after == before + 1
    reopened = read_snapshot(postgres_engine, snapshot["id"])
    assert reopened == snapshot
    assert metric_map(reopened)["quality_issue_count"]["value"] == before


def test_snapshot_hash_is_stable_and_persisted_row_is_immutable(
    postgres_engine, tmp_path
):
    fixture = setup_scope(postgres_engine, tmp_path, "immutable")
    run = execute_run(fixture, "cpu", lambda *args: [])
    scope = analytics_scope(fixture, run["run_id"])

    first = capture_snapshot(postgres_engine, scope)
    second = capture_snapshot(postgres_engine, scope)
    assert second == first
    assert first["payload_sha256"] == second["payload_sha256"]

    with pytest.raises(IntegrityError):
        with postgres_engine.begin() as connection:
            connection.execute(
                text("""
                    UPDATE analytics_snapshots
                    SET evidence_status = 'failed'
                    WHERE id = CAST(:id AS uuid)
                """),
                {"id": first["id"]},
            )
    with pytest.raises(IntegrityError):
        with postgres_engine.begin() as connection:
            connection.execute(
                text("DELETE FROM analytics_snapshots WHERE id = CAST(:id AS uuid)"),
                {"id": first["id"]},
            )

    with postgres_engine.connect() as connection:
        count = connection.scalar(
            text("""
                SELECT count(*)
                FROM analytics_snapshots
                WHERE payload_sha256 = :checksum
            """),
            {"checksum": first["payload_sha256"]},
        )
    assert count == 1
