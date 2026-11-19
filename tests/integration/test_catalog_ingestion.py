from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier

import pytest
from catalog_support import build_release, catalog_counts
from sqlalchemy import text

from worker.catalog import ingest, operation_status
from worker.catalog_store import CatalogBusy, CatalogConflict, writer
from worker.reconciliation import reconcile


def test_first_import_and_repeat_are_idempotent(postgres_engine, tmp_path):
    package, _ = build_release(tmp_path, "synthetic-t4-idempotent", 1)
    root = tmp_path / "artifacts"

    first = ingest(postgres_engine, root, package)
    first_counts = catalog_counts(postgres_engine)

    second = ingest(postgres_engine, root, package)
    second_counts = catalog_counts(postgres_engine)

    assert first["ok"] is True
    assert second["ok"] is True
    assert second_counts == first_counts

    status = operation_status(postgres_engine, package.run_id)
    assert status["operation"]["status"] == "succeeded"
    assert status["items"]["succeeded"] == len(package.unit_artifacts)
    assert status["items"]["pending"] == 0
    assert status["items"]["failed"] == 0


def test_interrupted_import_resumes_as_partial_then_succeeds(postgres_engine, tmp_path):
    package, _ = build_release(tmp_path, "synthetic-t4-resume", 1)
    root = tmp_path / "artifacts"
    stop_after = sorted(package.unit_artifacts)[1]
    interrupted = False

    def stop_once(stage, asset_id):
        nonlocal interrupted
        if stage == "before_publication" and asset_id == stop_after and not interrupted:
            interrupted = True
            raise RuntimeError("synthetic interruption")

    with pytest.raises(RuntimeError, match="synthetic interruption"):
        ingest(postgres_engine, root, package, hook=stop_once)

    failed_status = operation_status(postgres_engine, package.run_id)
    assert failed_status["operation"]["status"] == "partial"
    assert failed_status["items"]["succeeded"] >= 1
    assert failed_status["items"]["failed"] >= 1

    resumed = ingest(
        postgres_engine,
        root,
        package,
        resume_run=package.run_id,
    )
    assert resumed["ok"] is True

    final_status = operation_status(postgres_engine, package.run_id)
    assert final_status["operation"]["status"] == "succeeded"
    assert final_status["items"]["succeeded"] == len(package.unit_artifacts)
    assert final_status["items"]["failed"] == 0


def test_failure_before_item_commit_rolls_back_the_whole_item(
    postgres_engine, tmp_path
):
    package, _ = build_release(tmp_path, "synthetic-t4-rollback", 1)
    root = tmp_path / "artifacts"
    victim = sorted(package.unit_artifacts)[0]

    def fail_before_commit(stage, asset_id):
        if stage == "before_item_commit" and asset_id == victim:
            raise RuntimeError("synthetic failure before commit")

    with pytest.raises(RuntimeError, match="before commit"):
        ingest(postgres_engine, root, package, hook=fail_before_commit)

    version_id = package.specification()["version_id"]
    with postgres_engine.connect() as connection:
        for table in ("dataset_items", "annotation_revisions", "annotations"):
            rows = connection.scalar(
                text(
                    f"SELECT count(*) FROM {table} "
                    "WHERE dataset_version_id = CAST(:v AS uuid) "
                    "AND asset_id = CAST(:a AS uuid)"
                ),
                {"v": version_id, "a": victim},
            )
            assert rows == 0, table

    status = operation_status(postgres_engine, package.run_id)
    assert status["operation"]["status"] == "failed"
    assert status["items"]["succeeded"] == 0
    assert status["items"]["failed"] == 1

    assert ingest(postgres_engine, root, package, resume_run=package.run_id)["ok"]
    assert operation_status(postgres_engine, package.run_id)["operation"]["status"] == (
        "succeeded"
    )


def test_item_attempts_are_bounded(postgres_engine, tmp_path):
    package, _ = build_release(tmp_path, "synthetic-t4-attempts", 1)
    root = tmp_path / "artifacts"

    def always_fail(stage, asset_id):
        if stage == "before_publication":
            raise RuntimeError("synthetic persistent failure")

    for _ in range(3):
        with pytest.raises(RuntimeError, match="persistent failure"):
            ingest(postgres_engine, root, package, hook=always_fail)

    with pytest.raises(CatalogConflict, match="three recorded attempts"):
        ingest(postgres_engine, root, package)
    assert operation_status(postgres_engine, package.run_id)["operation"]["status"] in (
        "failed",
        "partial",
    )


def test_reconciliation_is_deterministic_and_read_only(postgres_engine, tmp_path):
    package, _ = build_release(tmp_path, "synthetic-t4-reconcile", 1)
    root = tmp_path / "artifacts"

    ingest(postgres_engine, root, package)

    before = catalog_counts(postgres_engine)
    first = reconcile(postgres_engine, root, package.specification())
    second = reconcile(postgres_engine, root, package.specification())
    after = catalog_counts(postgres_engine)

    assert first == second
    assert first["ok"] is True
    assert first["findings"] == []
    assert first["orphan_artifacts"] == []
    assert after == before


def test_reconciliation_reports_missing_corrupt_and_orphan_artifacts(
    postgres_engine, tmp_path
):
    package, _ = build_release(tmp_path, "synthetic-t4-integrity", 1)
    root = tmp_path / "artifacts"

    ingest(postgres_engine, root, package)

    checksum = sorted(package.blobs)[0]
    artifact = root / "catalog" / "objects" / checksum
    original = artifact.read_bytes()

    artifact.unlink()
    missing = reconcile(postgres_engine, root, package.specification())
    assert any(item["kind"] == "missing_artifact" for item in missing["findings"])

    artifact.write_bytes(original + b"corruption")
    corrupt = reconcile(postgres_engine, root, package.specification())
    assert any(item["kind"] == "corrupt_artifact" for item in corrupt["findings"])

    artifact.write_bytes(original)
    orphan = root / "catalog" / "objects" / ("f" * 64)
    orphan.write_bytes(b"orphan")
    report = reconcile(postgres_engine, root, package.specification())
    assert any(
        item["reason"] == "unregistered_artifact" for item in report["orphan_artifacts"]
    )


def test_completed_import_with_corrupt_artifact_is_reported_not_repaired(
    postgres_engine, tmp_path
):
    package, _ = build_release(tmp_path, "synthetic-t4-no-repair", 1)
    root = tmp_path / "artifacts"
    ingest(postgres_engine, root, package)

    artifact = root / "catalog" / "objects" / sorted(package.blobs)[0]
    artifact.write_bytes(b"corrupt")

    with pytest.raises(CatalogConflict, match="no longer reconciles"):
        ingest(postgres_engine, root, package)
    assert artifact.read_bytes() == b"corrupt"


def test_changed_expected_identity_is_rejected(postgres_engine, tmp_path):
    package, _ = build_release(tmp_path, "synthetic-t4-conflict", 1)
    root = tmp_path / "artifacts"

    ingest(postgres_engine, root, package)

    changed_rows = {
        **package.rows,
        "assets": [
            {
                **package.rows["assets"][0],
                "pixel_sha256": "f" * 64,
            },
            *package.rows["assets"][1:],
        ],
    }
    changed = replace(package, rows=changed_rows)

    with pytest.raises(CatalogConflict):
        ingest(postgres_engine, root, changed)


def test_resume_identity_must_match(postgres_engine, tmp_path):
    package, _ = build_release(tmp_path, "synthetic-t4-resume-identity", 1)
    root = tmp_path / "artifacts"

    with pytest.raises(CatalogConflict, match="does not match"):
        ingest(
            postgres_engine,
            root,
            package,
            resume_run="00000000-0000-0000-0000-000000000000",
        )


def test_second_writer_is_rejected_while_the_catalog_lock_is_held(
    postgres_engine, tmp_path
):
    package, _ = build_release(tmp_path, "synthetic-t4-lock", 1)
    root = tmp_path / "artifacts"

    with writer(postgres_engine):
        with pytest.raises(CatalogBusy):
            ingest(postgres_engine, root, package)
        assert not (root / "catalog").exists()
        # Reads are not blocked by the writer lock.
        with pytest.raises(ValueError, match="unknown ingestion operation"):
            operation_status(postgres_engine, package.run_id)

    assert ingest(postgres_engine, root, package)["ok"] is True


def test_concurrent_importers_serialize_without_duplicate_rows(
    postgres_engine, tmp_path
):
    package, _ = build_release(tmp_path, "synthetic-t4-concurrent", 1)
    root = tmp_path / "artifacts"
    barrier = Barrier(2)

    def attempt(_):
        barrier.wait()
        try:
            return ingest(postgres_engine, root, package)
        except CatalogBusy as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, range(2)))

    assert any(isinstance(result, dict) and result["ok"] for result in results)
    assert all(
        isinstance(result, CatalogBusy) or result["ok"] is True for result in results
    )

    report = reconcile(postgres_engine, root, package.specification())
    assert report["ok"] is True
    assert report["findings"] == []
    status = operation_status(postgres_engine, package.run_id)
    assert status["operation"]["status"] == "succeeded"
    assert status["items"]["succeeded"] == len(package.unit_artifacts)
