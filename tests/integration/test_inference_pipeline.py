"""End-to-end synthetic batch inference, recovery and overlay evidence."""

from __future__ import annotations

from uuid import uuid4

import pytest
from catalog_support import build_release
from PIL import Image
from sqlalchemy import text

from worker.catalog import ingest
from worker.catalog_store import CatalogConflict
from worker.detection_overlay import generate_overlays
from worker.inference import (
    inference_status,
    reconcile_run,
    register_batch,
    register_model_contract,
    run_inference,
)
from worker.validation import CLASSES, sha256


def fixture(postgres_engine, tmp_path):
    package, _ = build_release(tmp_path, "synthetic-m3t3-pipeline", 1)
    root = tmp_path / "artifacts"
    ingest(postgres_engine, root, package)
    batch = register_batch(
        postgres_engine,
        root,
        package.version_id,
        "test",
    )
    checkpoint = tmp_path / "checkpoint.pt"
    checkpoint.write_bytes(b"m3t3-synthetic-checkpoint")
    contract = {
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
            "settings": {"imgsz": 320, "conf": 0.001, "iou": 0.7, "max_det": 300},
            "confidence_threshold": 0.07,
            "match_iou": 0.5,
        },
    }
    model = register_model_contract(
        postgres_engine,
        root,
        package.version_id,
        contract,
    )
    return root, batch, model


def prediction(index):
    if index == 0:
        return []
    return [
        {"cls": 1, "conf": 0.9, "box": [0, 0, 10, 10]},
        {"cls": 3, "conf": 0.7, "box": [2, 2, 12, 12]},
        {"cls": 5, "conf": 0.06, "box": [4, 4, 8, 8]},
    ]


def test_vertical_slice_persists_zero_and_multiple_detections_and_overlays(
    postgres_engine, tmp_path
):
    root, batch, model = fixture(postgres_engine, tmp_path)
    calls = 0
    original_images = {}
    with postgres_engine.connect() as connection:
        for checksum in connection.scalars(
            text("""
                SELECT bi.image_sha256
                FROM batch_items AS bi
                WHERE bi.batch_id = CAST(:batch AS uuid)
            """),
            {"batch": batch["batch_id"]},
        ):
            original_images[checksum] = sha256(
                (root / "catalog/objects" / checksum).read_bytes()
            )

    def predictor(path, settings, device):
        nonlocal calls
        output = prediction(calls)
        calls += 1
        return output

    report = run_inference(
        postgres_engine,
        root,
        batch["batch_id"],
        model["id"],
        "cpu",
        predictor=predictor,
    )
    assert report["ok"] is True
    assert calls == batch["member_count"]

    status = inference_status(postgres_engine, report["run_id"])
    assert status["operation"]["status"] == "succeeded"
    assert status["items"]["succeeded"] == batch["member_count"]
    assert status["items"]["failed"] == 0

    with postgres_engine.connect() as connection:
        rows = connection.execute(
            text("""
                SELECT status, raw_prediction_count, detection_count
                FROM image_results
                WHERE run_id = CAST(:run AS uuid)
                ORDER BY asset_id
            """),
            {"run": report["run_id"]},
        ).all()
        assert any(
            row.status == "succeeded"
            and row.raw_prediction_count == 0
            and row.detection_count == 0
            for row in rows
        )
        assert any(row.detection_count == 2 for row in rows)
        detections = connection.execute(
            text("""
                SELECT class_id, confidence, box_xmin, box_ymin,
                       box_xmax, box_ymax
                FROM detections
                WHERE run_id = CAST(:run AS uuid)
                ORDER BY asset_id, ordinal
            """),
            {"run": report["run_id"]},
        ).all()
        assert {row.class_id for row in detections} == {1, 3}
        assert min(row.confidence for row in detections) >= 0.7
        assert all(row.box_xmax > row.box_xmin for row in detections)

    def forbidden(*args):
        raise AssertionError("completed inference must not run the detector again")

    repeated = run_inference(
        postgres_engine,
        root,
        batch["batch_id"],
        model["id"],
        "cpu",
        predictor=forbidden,
    )
    assert repeated == report
    with postgres_engine.connect() as connection:
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM image_results "
                    "WHERE run_id = CAST(:run AS uuid)"
                ),
                {"run": report["run_id"]},
            )
            == batch["member_count"]
        )

    overlays = generate_overlays(
        postgres_engine,
        root,
        report["run_id"],
    )
    assert len(overlays["overlays"]) == batch["member_count"]
    for item in overlays["overlays"]:
        overlay_path = root / "catalog/objects" / item["sha256"]
        with Image.open(overlay_path) as image:
            assert image.format == "PNG"
            assert image.size == (16, 16)

    repeated_overlays = generate_overlays(
        postgres_engine,
        root,
        report["run_id"],
    )
    assert repeated_overlays == overlays
    with postgres_engine.connect() as connection:
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM image_overlays "
                    "WHERE run_id = CAST(:run AS uuid)"
                ),
                {"run": report["run_id"]},
            )
            == batch["member_count"]
        )

    for checksum, digest in original_images.items():
        assert sha256((root / "catalog/objects" / checksum).read_bytes()) == digest

    final = reconcile_run(postgres_engine, root, report["run_id"])
    assert final["ok"] is True
    assert final["counts"]["overlays"] == batch["member_count"]


def test_interrupted_post_commit_resume_preserves_success(postgres_engine, tmp_path):
    root, batch, model = fixture(postgres_engine, tmp_path)
    interrupted = False

    def stop_once(stage, asset_id):
        nonlocal interrupted
        if stage == "after_item_commit" and not interrupted:
            interrupted = True
            raise RuntimeError("simulated process interruption")

    with pytest.raises(RuntimeError, match="interruption"):
        run_inference(
            postgres_engine,
            root,
            batch["batch_id"],
            model["id"],
            "mps",
            predictor=lambda *args: [],
            hook=stop_once,
        )

    with postgres_engine.connect() as connection:
        run_id = connection.scalar(
            text("""
                SELECT id
                FROM inference_runs
                WHERE batch_id = CAST(:batch AS uuid)
                  AND model_id = CAST(:model AS uuid)
            """),
            {"batch": batch["batch_id"], "model": model["id"]},
        )
    status = inference_status(postgres_engine, run_id)
    assert status["operation"]["status"] == "partial"
    assert status["items"]["succeeded"] == 1

    calls = 0

    def after_restart(*args):
        nonlocal calls
        calls += 1
        return []

    resumed = run_inference(
        postgres_engine,
        root,
        batch["batch_id"],
        model["id"],
        "mps",
        predictor=after_restart,
        resume_run=run_id,
    )
    assert resumed["ok"] is True
    assert calls == batch["member_count"] - 1
    final = inference_status(postgres_engine, run_id)
    assert final["operation"]["status"] == "succeeded"
    assert final["items"]["succeeded"] == batch["member_count"]


def test_malformed_output_is_a_failed_item_and_can_resume(postgres_engine, tmp_path):
    root, batch, model = fixture(postgres_engine, tmp_path)
    calls = 0

    def malformed_once(path, settings, device):
        nonlocal calls
        calls += 1
        if calls == 1:
            return [{"cls": 0, "conf": 0.9, "box": [3, 3, 2, 8]}]
        return []

    report = run_inference(
        postgres_engine,
        root,
        batch["batch_id"],
        model["id"],
        "cpu",
        predictor=malformed_once,
    )
    assert report["ok"] is False
    status = inference_status(postgres_engine, report["run_id"])
    assert status["operation"]["status"] == "partial"
    assert status["items"]["failed"] == 1
    with pytest.raises(CatalogConflict, match="resume run identity"):
        run_inference(
            postgres_engine,
            root,
            batch["batch_id"],
            model["id"],
            "cpu",
            predictor=lambda *args: [],
            resume_run=uuid4(),
        )

    resumed = run_inference(
        postgres_engine,
        root,
        batch["batch_id"],
        model["id"],
        "cpu",
        predictor=lambda *args: [],
        resume_run=report["run_id"],
    )
    assert resumed["ok"] is True
    with postgres_engine.connect() as connection:
        attempts = (
            connection.execute(
                text("""
                SELECT attempts
                FROM image_results
                WHERE run_id = CAST(:run AS uuid)
                ORDER BY asset_id
            """),
                {"run": report["run_id"]},
            )
            .scalars()
            .all()
        )
    assert sorted(attempts) == [1] * (batch["member_count"] - 1) + [2]


def test_items_exhaust_three_recorded_attempts_without_silent_retry(
    postgres_engine, tmp_path
):
    root, batch, model = fixture(postgres_engine, tmp_path)
    calls = 0

    def always_malformed(*args):
        nonlocal calls
        calls += 1
        return [{"cls": 0, "conf": 2, "box": [0, 0, 1, 1]}]

    reports = []
    for attempt in range(3):
        reports.append(
            run_inference(
                postgres_engine,
                root,
                batch["batch_id"],
                model["id"],
                "cpu",
                predictor=always_malformed,
                resume_run=reports[-1]["run_id"] if attempt else None,
            )
        )
    exhausted = calls
    fourth = run_inference(
        postgres_engine,
        root,
        batch["batch_id"],
        model["id"],
        "cpu",
        predictor=lambda *args: [],
        resume_run=reports[-1]["run_id"],
    )
    assert fourth["ok"] is False
    assert calls == exhausted
    status = inference_status(postgres_engine, fourth["run_id"])
    assert status["items"]["failed"] == batch["member_count"]
    with postgres_engine.connect() as connection:
        assert set(
            connection.scalars(
                text("""
                    SELECT attempts
                    FROM image_results
                    WHERE run_id = CAST(:run AS uuid)
                """),
                {"run": fourth["run_id"]},
            )
        ) == {3}


def test_corruption_is_reported_not_repaired(postgres_engine, tmp_path):
    root, batch, model = fixture(postgres_engine, tmp_path)
    report = run_inference(
        postgres_engine,
        root,
        batch["batch_id"],
        model["id"],
        "cpu",
        predictor=lambda *args: [],
    )
    checkpoint = root / "catalog/objects" / model["checkpoint_sha256"]
    original = checkpoint.read_bytes()
    checkpoint.write_bytes(original + b"corrupt")

    broken = reconcile_run(postgres_engine, root, report["run_id"])
    assert broken["ok"] is False
    assert any(item["kind"] == "corrupt_checkpoint" for item in broken["findings"])

    with pytest.raises(CatalogConflict, match="no longer reconciles"):
        run_inference(
            postgres_engine,
            root,
            batch["batch_id"],
            model["id"],
            "cpu",
            predictor=lambda *args: [],
        )
    assert checkpoint.read_bytes() == original + b"corrupt"


def test_overlay_corruption_is_reconciled(postgres_engine, tmp_path):
    root, batch, model = fixture(postgres_engine, tmp_path)
    report = run_inference(
        postgres_engine,
        root,
        batch["batch_id"],
        model["id"],
        "cpu",
        predictor=lambda *args: [],
    )
    overlay = generate_overlays(postgres_engine, root, report["run_id"])["overlays"][0]
    path = root / "catalog/objects" / overlay["sha256"]
    original = path.read_bytes()
    path.write_bytes(original + b"corrupt")

    broken = reconcile_run(postgres_engine, root, report["run_id"])
    assert broken["ok"] is False
    assert any(item["kind"] == "corrupt_overlay" for item in broken["findings"])
    path.write_bytes(original)
    assert reconcile_run(postgres_engine, root, report["run_id"])["ok"] is True
