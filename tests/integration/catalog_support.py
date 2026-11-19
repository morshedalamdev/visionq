"""Shared builders for the isolated T4 catalog integration tests."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from sqlalchemy import text

from worker.catalog_input import load_package, synthetic_sources
from worker.inventory import canonical_json, inventory
from worker.preparation import export, prepare
from worker.review import make_packet
from worker.validation import audit, sha256

CATALOG_TABLES = (
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


def version_count(engine, version_id):
    with engine.connect() as connection:
        return connection.scalar(
            text("SELECT count(*) FROM dataset_versions WHERE id = CAST(:id AS uuid)"),
            {"id": version_id},
        )


def catalog_counts(engine):
    with engine.connect() as connection:
        return {
            table: connection.exec_driver_sql(
                f"SELECT count(*) FROM {table}"
            ).scalar_one()
            for table in CATALOG_TABLES
        }
