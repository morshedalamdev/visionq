from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest

from worker.catalog import ingest, operation_status
from worker.catalog_input import load_package, synthetic_sources
from worker.catalog_store import CatalogConflict
from worker.db import database
from worker.inventory import canonical_json, inventory
from worker.preparation import export, prepare
from worker.reconciliation import reconcile
from worker.review import make_packet
from worker.validation import audit, sha256


def build_release(tmp_path: Path, dataset_name: str, version: int):
    source = tmp_path / "source"
    (source / "IMAGES").mkdir(parents=True)
    (source / "ANNOTATIONS").mkdir()

    for relative_path, data in synthetic_sources().items():
        destination = source / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)

    manifest, _ = inventory(source)
    baseline = tmp_path / "baseline.json"
    baseline.write_bytes(canonical_json(manifest))

    report = audit(
        source,
        baseline,
        sha256(baseline.read_bytes()),
        "one-based-inclusive",
    )
    report_path = tmp_path / "audit.json"
    report_path.write_bytes(canonical_json(report))

    packet = tmp_path / "packet"
    make_packet(source, report_path, packet)

    review_path = packet / "review.json"
    review = json.loads(review_path.read_bytes())
    review.update(
        reviewer="Synthetic fixture",
        reviewed_at="2026-11-19T12:00:00+08:00",
        coordinate_basis="Known synthetic one-based-inclusive boxes",
        warning_disposition="Expected synthetic class-count warnings",
    )
    for item in review["items"]:
        item.update(decision="accept", notes="Synthetic known annotation")
    review_path.write_bytes(canonical_json(review))

    plan = prepare(source, packet)
    plan_path = tmp_path / "plan.json"
    plan_path.write_bytes(canonical_json(plan))

    release = tmp_path / "release"
    result = export(
        source,
        packet,
        plan_path,
        sha256(plan_path.read_bytes()),
        release,
    )

    package = load_package(
        source=source,
        baseline=baseline,
        packet=packet,
        release=release,
        release_sha256=result["manifest_sha256"],
        dataset_name=f"{dataset_name}-{uuid4().hex}",
        version=version,
    )
    return package, release


@pytest.fixture
def postgres_engine():
    if pytest.importorskip("psycopg") is None:
        pytest.fail("psycopg is required")

    if os.environ.get("VISIONQ_T4_SCHEMA_TEST") != "1":
        pytest.skip("requires the isolated T4 PostgreSQL database")

    if not os.environ.get("VISIONQ_DATABASE_URL"):
        pytest.fail("VISIONQ_DATABASE_URL must be explicit")

    engine = database()
    if engine.url.database != "visionq_t4_test":
        engine.dispose()
        pytest.fail("tests require database visionq_t4_test")
    if engine.url.host not in ("127.0.0.1", "localhost"):
        engine.dispose()
        pytest.fail("tests require loopback PostgreSQL")

    yield engine
    engine.dispose()


def catalog_counts(engine):
    tables = (
        "catalog_artifacts",
        "dataset_versions",
        "assets",
        "annotation_revisions",
        "annotations",
        "dataset_groups",
        "dataset_items",
        "quality_issues",
        "ingestion_runs",
        "ingestion_items",
    )
    with engine.connect() as connection:
        return {
            table: connection.exec_driver_sql(
                f"SELECT count(*) FROM {table}"
            ).scalar_one()
            for table in tables
        }


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
