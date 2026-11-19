"""Rights-classified catalog snapshots and create-only backup recovery."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from uuid import UUID

from sqlalchemy import select, text

from worker.backup import Azure, Directory
from worker.catalog_store import ensure_row, read_rows, tables, writer
from worker.fixture import publish
from worker.inventory import canonical_json
from worker.reconciliation import compare_rows, reconcile_connection
from worker.validation import sha256

BACKUP_FORMAT = "visionq-catalog-backup-v1"
RIGHTS_FORMAT = "visionq-catalog-rights-v1"
MANIFEST = "manifest.json"
COMPLETE = "COMPLETE"

MANIFEST_MEMBERS = (
    "specification.json",
    "catalog.json",
    "rights.json",
)

CATALOG_RESTORE_ORDER = (
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


def validate_backup_id(backup_id: str) -> str:
    value = str(UUID(backup_id))
    if value != backup_id:
        raise ValueError("backup_id must use canonical UUID text")
    return value


def prefix(backup_id: str) -> str:
    backup_id = validate_backup_id(backup_id)
    return f"m2t4/{backup_id}/"


def object_member(checksum: str) -> str:
    if len(checksum) != 64 or any(
        character not in "0123456789abcdef" for character in checksum
    ):
        raise ValueError("invalid catalog object checksum")
    return f"objects/{checksum}"


def rights_for_package(package) -> dict:
    specification = package.specification()
    versions = specification["rows"]["dataset_versions"]
    if len(versions) != 1:
        raise ValueError("catalog package has no unique dataset version")

    evidence_kind = versions[0]["evidence_kind"]
    if evidence_kind != "synthetic":
        raise ValueError(
            "released catalog backup blocked: artifact rights clearance is absent"
        )

    return {
        "format": RIGHTS_FORMAT,
        "evidence_kind": "synthetic",
        "classification": "synthetic-only",
        "included_categories": sorted(set(package.categories.values())),
        "excluded_categories": [],
    }


def snapshot_catalog(engine, specification):
    with engine.connect() as connection:
        connection = connection.execution_options(isolation_level="REPEATABLE READ")
        with connection.begin():
            connection.execute(text("SET TRANSACTION READ ONLY"))
            snapshot = read_rows(connection, specification)
    return snapshot


def read_verified_member(store, base: str, name: str, expected):
    try:
        data = store.get(base + name)
    except FileNotFoundError:
        raise ValueError(f"backup member missing: {name}") from None
    if sha256(data) != expected["sha256"]:
        raise ValueError(f"backup checksum mismatch: {name}")
    if len(data) != expected["bytes"]:
        raise ValueError(f"backup size mismatch: {name}")
    return data


def read_verified_bundle(store, backup_id: str):
    base = prefix(backup_id)

    try:
        marker = store.get(base + COMPLETE)
    except FileNotFoundError:
        raise ValueError("incomplete backup: COMPLETE missing") from None

    manifest = store.get(base + MANIFEST)
    manifest_sha = sha256(manifest)
    if marker != manifest_sha.encode("ascii"):
        raise ValueError("manifest checksum mismatch")

    try:
        inventory = json.loads(manifest)
    except json.JSONDecodeError:
        raise ValueError("backup manifest is invalid JSON") from None

    if (
        not isinstance(inventory, dict)
        or inventory.get("format") != BACKUP_FORMAT
        or inventory.get("backup_id") != backup_id
        or not isinstance(inventory.get("members"), dict)
        or set(inventory["members"]) != set(MANIFEST_MEMBERS)
        or not isinstance(inventory.get("objects"), dict)
    ):
        raise ValueError("unexpected backup inventory")

    specification_bytes = read_verified_member(
        store,
        base,
        "specification.json",
        inventory["members"]["specification.json"],
    )
    catalog_bytes = read_verified_member(
        store,
        base,
        "catalog.json",
        inventory["members"]["catalog.json"],
    )
    rights_bytes = read_verified_member(
        store,
        base,
        "rights.json",
        inventory["members"]["rights.json"],
    )

    specification = json.loads(specification_bytes)
    catalog = json.loads(catalog_bytes)
    rights = json.loads(rights_bytes)

    if specification.get("format") != "visionq-catalog-package-v1":
        raise ValueError("unsupported catalog package specification")
    if rights.get("format") != RIGHTS_FORMAT:
        raise ValueError("unsupported rights manifest")
    if rights.get("evidence_kind") != "synthetic":
        raise ValueError("released backup restore requires approved rights")
    if rights.get("classification") != "synthetic-only":
        raise ValueError("unsupported catalog rights classification")

    if inventory["dataset_version_id"] != specification["version_id"]:
        raise ValueError("backup dataset identity differs")
    if inventory["run_id"] != specification["run_id"]:
        raise ValueError("backup operation identity differs")

    findings = compare_rows(specification, catalog, require_success=True)
    if findings:
        raise ValueError("catalog snapshot differs from package specification")

    expected_objects = {
        checksum: {
            "sha256": checksum,
            "bytes": artifact["bytes"],
        }
        for checksum, artifact in specification["artifacts"].items()
    }
    if inventory["objects"] != expected_objects:
        raise ValueError("backup object inventory differs")

    for checksum, expected in expected_objects.items():
        read_verified_member(
            store,
            base,
            object_member(checksum),
            expected,
        )

    return manifest_sha, specification, catalog, rights, inventory


def backup_catalog(engine, store, backup_id: str, package) -> str:
    backup_id = validate_backup_id(backup_id)
    base = prefix(backup_id)

    try:
        store.get(base + COMPLETE)
        raise FileExistsError("catalog backup already exists")
    except FileNotFoundError:
        pass

    specification = package.specification()
    rights = rights_for_package(package)

    with engine.connect() as connection:
        connection = connection.execution_options(isolation_level="REPEATABLE READ")
        with connection.begin():
            connection.execute(text("SET TRANSACTION READ ONLY"))
            report = reconcile_connection(
                connection,
                root=None,
                spec=specification,
            )
    if not report["ok"]:
        raise ValueError("catalog is not complete and reconciled")

    snapshot = snapshot_catalog(engine, specification)

    specification_data = canonical_json(specification)
    catalog_data = canonical_json(snapshot)
    rights_data = canonical_json(rights)

    members = {
        "specification.json": {
            "sha256": sha256(specification_data),
            "bytes": len(specification_data),
        },
        "catalog.json": {
            "sha256": sha256(catalog_data),
            "bytes": len(catalog_data),
        },
        "rights.json": {
            "sha256": sha256(rights_data),
            "bytes": len(rights_data),
        },
    }

    store.put(base + "specification.json", specification_data)
    store.put(base + "catalog.json", catalog_data)
    store.put(base + "rights.json", rights_data)

    objects = {}
    for checksum, artifact in sorted(specification["artifacts"].items()):
        data = package.blobs[checksum]
        if sha256(data) != checksum:
            raise ValueError("package object differs from its checksum")
        if len(data) != artifact["bytes"]:
            raise ValueError("package object size differs")
        store.put(base + object_member(checksum), data)
        objects[checksum] = {
            "sha256": checksum,
            "bytes": len(data),
        }

    manifest = canonical_json(
        {
            "format": BACKUP_FORMAT,
            "backup_id": backup_id,
            "dataset_version_id": specification["version_id"],
            "run_id": specification["run_id"],
            "rights": rights,
            "members": members,
            "objects": objects,
        }
    )
    manifest_sha = sha256(manifest)

    store.put(base + MANIFEST, manifest)

    if store.get(base + MANIFEST) != manifest:
        raise ValueError("uploaded manifest differs")

    store.put(base + COMPLETE, manifest_sha.encode("ascii"))

    if store.get(base + COMPLETE) != manifest_sha.encode("ascii"):
        raise ValueError("uploaded completion marker differs")

    return manifest_sha


def verify_catalog_backup(store, backup_id: str) -> str:
    manifest_sha, _, _, _, _ = read_verified_bundle(store, backup_id)
    return manifest_sha


def restore_catalog(
    engine,
    store,
    backup_id: str,
    destination: Path,
) -> str:
    manifest_sha, specification, catalog, rights, inventory = read_verified_bundle(
        store, backup_id
    )

    if destination.exists():
        raise FileExistsError(destination)

    destination.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(dir=destination.parent) as tmpdir:
        staged = Path(tmpdir) / "bundle"
        staged.mkdir()

        base = prefix(backup_id)
        publish(
            staged / "catalog" / "manifest.json",
            canonical_json(inventory),
        )
        publish(
            staged / "catalog" / "specification.json",
            canonical_json(specification),
        )
        publish(
            staged / "catalog" / "rights.json",
            canonical_json(rights),
        )
        publish(
            staged / "catalog" / "snapshot.json",
            canonical_json(catalog),
        )

        for checksum, expected in inventory["objects"].items():
            data = store.get(base + object_member(checksum))
            if sha256(data) != expected["sha256"]:
                raise ValueError(f"restored object mismatch: {checksum}")
            if len(data) != expected["bytes"]:
                raise ValueError(f"restored object size mismatch: {checksum}")
            publish(staged / "catalog" / "objects" / checksum, data)

        destination.mkdir()
        try:
            with writer(engine) as connection:
                with connection.begin():
                    reflected = tables(connection)
                    version_id = specification["version_id"]

                    existing = (
                        connection.execute(
                            select(reflected["dataset_versions"]).where(
                                reflected["dataset_versions"].c.id == UUID(version_id)
                            )
                        )
                        .mappings()
                        .one_or_none()
                    )
                    if existing is not None:
                        raise ValueError(
                            "catalog restore destination already contains version"
                        )

                    for name in CATALOG_RESTORE_ORDER:
                        table = reflected[name]
                        for row in catalog[name]:
                            ensure_row(connection, table, row)

                    report = reconcile_connection(
                        connection,
                        staged,
                        specification,
                    )
                    if not report["ok"]:
                        raise ValueError("restored catalog does not reconcile")

            try:
                staged.replace(destination)
            except OSError:
                destination.rmdir()
                raise
        except Exception:
            if destination.exists():
                try:
                    destination.rmdir()
                except OSError:
                    pass
            raise

    return manifest_sha
