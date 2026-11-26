"""Rights-classified catalog snapshots and create-only backup recovery.

Restore ordering: PostgreSQL and the filesystem cannot commit together, and the
catalog triggers forbid deleting committed rows. Restore therefore publishes the
verified artifact tree first (marked ``pending``) and commits the database last.
Every failure window is either rolled back completely or left in a state that
rerunning the same restore detects and finishes.
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import tempfile
from pathlib import Path
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert

from worker.backup import Directory
from worker.catalog_store import (
    check_blob,
    ensure_row,
    read_rows,
    tables,
    values_for,
    writer,
)
from worker.fixture import publish
from worker.inventory import canonical_json
from worker.reconciliation import compare_rows, reconcile_connection
from worker.validation import sha256

BACKUP_FORMAT = "visionq-catalog-backup-v1"
RIGHTS_FORMAT = "visionq-catalog-rights-v1"
RESTORE_STATE_FORMAT = "visionq-catalog-restore-state-v1"
MANIFEST = "manifest.json"
COMPLETE = "COMPLETE"
RESTORE_STATE = "catalog/RESTORE_STATE.json"

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


class RestoreIncomplete(RuntimeError):
    """The restore needs to be rerun; the destination was left for resumption."""


# Server-assigned insertion times differ between clusters, so a content-addressed
# row that already exists keeps its first value instead of conflicting.
VOLATILE_COLUMNS = frozenset({"created_at"})


def restore_row(connection, table, row) -> None:
    connection.execute(
        insert(table).values(**values_for(table, row)).on_conflict_do_nothing()
    )
    ensure_row(
        connection,
        table,
        {name: value for name, value in row.items() if name not in VOLATILE_COLUMNS},
    )


def validate_backup_id(backup_id: str) -> str:
    try:
        value = str(UUID(backup_id))
    except (ValueError, AttributeError, TypeError):
        raise ValueError("backup_id must be a canonical UUID") from None
    if value != backup_id:
        raise ValueError("backup_id must use canonical lowercase UUID text")
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


def rights_for_specification(specification):
    versions = specification["rows"]["dataset_versions"]
    if len(versions) != 1:
        raise ValueError("catalog package has no unique dataset version")
    kind = versions[0]["evidence_kind"]
    categories = sorted(
        {c for a in specification["artifacts"].values() for c in a["categories"]}
    )
    result = {
        "format": RIGHTS_FORMAT,
        "evidence_kind": kind,
        "classification": "synthetic-only",
        "included_categories": categories,
        "excluded_categories": [],
    }
    if kind != "synthetic":
        from worker.real_release import RELEASE_SHA, SOURCE_SHA

        version = versions[0]
        if (
            kind,
            version["dataset_name"],
            version["version"],
            version["release_manifest_sha256"],
            version["source_manifest_sha256"],
        ) != ("released", "NEU-DET", 1, RELEASE_SHA, SOURCE_SHA):
            raise ValueError("rights clearance requires authorized NEU-DET v1")
        result.update(
            classification="owner-authorized-private-local-only",
            cloud_authorized=False,
            redistribution_terms="unresolved",
            authorization="Owner M2.T4 Real Dataset Ingestion and Module Closure: local backup and disposable restore",
            category_permissions={
                c: {"local_backup_restore": True, "cloud_upload": False}
                for c in categories
            },
        )
    return result


def rights_for_package(package):
    return rights_for_specification(package.specification())


def reconciled_snapshot(engine, root: Path, specification):
    """Reconcile and read rows in one repeatable-read, read-only transaction."""
    with engine.connect() as connection:
        connection = connection.execution_options(isolation_level="REPEATABLE READ")
        with connection.begin():
            connection.execute(text("SET TRANSACTION READ ONLY"))
            connection.execute(text("SET LOCAL TIME ZONE 'UTC'"))
            report = reconcile_connection(connection, root, specification)
            snapshot = read_rows(connection, specification)
    return report, snapshot


def snapshot_catalog(engine, specification):
    with engine.connect() as connection:
        connection = connection.execution_options(isolation_level="REPEATABLE READ")
        with connection.begin():
            connection.execute(text("SET TRANSACTION READ ONLY"))
            connection.execute(text("SET LOCAL TIME ZONE 'UTC'"))
            snapshot = read_rows(connection, specification)
    return snapshot


def member_exists(store, key: str) -> bool:
    try:
        store.get(key)
    except FileNotFoundError:
        return False
    return True


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


def load_json(data: bytes, name: str):
    try:
        return json.loads(data)
    except ValueError:
        raise ValueError(f"backup member is invalid JSON: {name}") from None


def load_bundle(store, backup_id: str, manifest: bytes):
    """Verify every member and object named by a manifest; no side effects."""
    base = prefix(backup_id)
    try:
        inventory = load_json(manifest, MANIFEST)
        if (
            not isinstance(inventory, dict)
            or inventory.get("format") != BACKUP_FORMAT
            or inventory.get("backup_id") != backup_id
            or not isinstance(inventory.get("members"), dict)
            or set(inventory["members"]) != set(MANIFEST_MEMBERS)
            or not isinstance(inventory.get("objects"), dict)
        ):
            raise ValueError("unexpected backup inventory")

        specification, catalog, rights = (
            load_json(
                read_verified_member(store, base, name, inventory["members"][name]),
                name,
            )
            for name in MANIFEST_MEMBERS
        )

        if specification.get("format") != "visionq-catalog-package-v1":
            raise ValueError("unsupported catalog package specification")
        if rights.get("format") != RIGHTS_FORMAT:
            raise ValueError("unsupported rights manifest")
        expected_rights = rights_for_specification(specification)
        if rights.get("evidence_kind") != expected_rights["evidence_kind"]:
            raise ValueError("released backup restore requires approved rights")
        if rights.get("classification") != expected_rights["classification"]:
            raise ValueError("unsupported catalog rights classification")
        if rights != expected_rights:
            raise ValueError("backup rights classification differs")
        if rights["evidence_kind"] != "synthetic" and type(store) is not Directory:
            raise ValueError("real catalog backup/restore is local-directory only")
        if inventory.get("rights") != rights:
            raise ValueError("backup rights manifest differs")

        if inventory["dataset_version_id"] != specification["version_id"]:
            raise ValueError("backup dataset identity differs")
        if inventory["run_id"] != specification["run_id"]:
            raise ValueError("backup operation identity differs")

        if set(catalog) != set(CATALOG_RESTORE_ORDER):
            raise ValueError("backup catalog snapshot has unexpected tables")
        if compare_rows(specification, catalog, require_success=True):
            raise ValueError("catalog snapshot differs from package specification")

        expected_objects = {
            checksum: {"sha256": checksum, "bytes": artifact["bytes"]}
            for checksum, artifact in specification["artifacts"].items()
        }
        if inventory["objects"] != expected_objects:
            raise ValueError("backup object inventory differs")
        for checksum, expected in expected_objects.items():
            read_verified_member(store, base, object_member(checksum), expected)
    except (KeyError, TypeError, AttributeError):
        raise ValueError("malformed catalog backup") from None

    return specification, catalog, rights, inventory


def read_verified_bundle(store, backup_id: str):
    base = prefix(backup_id)
    try:
        marker = store.get(base + COMPLETE)
    except FileNotFoundError:
        raise ValueError("incomplete backup: COMPLETE missing") from None
    try:
        manifest = store.get(base + MANIFEST)
    except FileNotFoundError:
        raise ValueError(f"backup member missing: {MANIFEST}") from None

    manifest_sha = sha256(manifest)
    if marker != manifest_sha.encode("ascii"):
        raise ValueError("manifest checksum mismatch")
    return (manifest_sha, *load_bundle(store, backup_id, manifest))


def backup_catalog(
    engine,
    root: Path,
    store,
    backup_id: str,
    package,
) -> str:
    backup_id = validate_backup_id(backup_id)
    base = prefix(backup_id)
    rights = rights_for_package(package)
    if rights["evidence_kind"] != "synthetic" and type(store) is not Directory:
        raise ValueError("real catalog backup/restore is local-directory only")

    if member_exists(store, base + COMPLETE):
        raise FileExistsError("catalog backup already exists")
    if member_exists(store, base + MANIFEST_MEMBERS[0]):
        raise FileExistsError(
            "an earlier attempt left an incomplete backup; choose a new backup id"
        )

    specification = package.specification()

    report, snapshot = reconciled_snapshot(engine, root, specification)
    if not report["ok"]:
        raise ValueError(
            "catalog is not complete and reconciled "
            f"({len(report['findings'])} findings, "
            f"{len(report['orphan_artifacts'])} orphans); run catalog-reconcile"
        )

    payloads = {
        "specification.json": canonical_json(specification),
        "catalog.json": canonical_json(snapshot),
        "rights.json": canonical_json(rights),
    }
    members = {
        name: {"sha256": sha256(data), "bytes": len(data)}
        for name, data in payloads.items()
    }
    for name, data in payloads.items():
        store.put(base + name, data)

    objects = {}
    for checksum, artifact in sorted(specification["artifacts"].items()):
        data = package.blobs[checksum]
        if sha256(data) != checksum:
            raise ValueError("package object differs from its checksum")
        if len(data) != artifact["bytes"]:
            raise ValueError("package object size differs")
        store.put(base + object_member(checksum), data)
        objects[checksum] = {"sha256": checksum, "bytes": len(data)}

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

    # Verify the complete bundle before the marker makes it visible.
    load_bundle(store, backup_id, manifest)

    store.put(base + COMPLETE, manifest_sha.encode("ascii"))
    if store.get(base + COMPLETE) != manifest_sha.encode("ascii"):
        raise ValueError("uploaded completion marker differs")

    return manifest_sha


def verify_catalog_backup(store, backup_id: str) -> str:
    manifest_sha, *_ = read_verified_bundle(store, backup_id)
    return manifest_sha


def restore_state_bytes(backup_id, manifest_sha, token, state) -> bytes:
    return canonical_json(
        {
            "format": RESTORE_STATE_FORMAT,
            "backup_id": backup_id,
            "manifest_sha256": manifest_sha,
            "token": token,
            "state": state,
        }
    )


def read_restore_state(destination: Path):
    """Return the destination's restore state, or None when it is not a restore."""
    try:
        state = json.loads((destination / RESTORE_STATE).read_bytes())
    except (FileNotFoundError, NotADirectoryError):
        return None
    except ValueError:
        raise ValueError("restore state file is unreadable") from None
    if not isinstance(state, dict) or state.get("format") != RESTORE_STATE_FORMAT:
        raise ValueError("unsupported restore state file")
    return state


def version_present(connection, version_id: str) -> bool:
    return (
        connection.scalar(
            text("SELECT 1 FROM dataset_versions WHERE id = CAST(:id AS uuid)"),
            {"id": version_id},
        )
        is not None
    )


def database_outcome(engine, version_id: str):
    """True/False when the commit outcome is known, None when it cannot be read."""
    try:
        with engine.connect() as connection:
            return version_present(connection, version_id)
    except Exception:
        return None


def stage_restore(store, backup_id, parent, manifest_sha, inventory, token):
    """Build the artifact tree privately and verify each object after writing."""
    base = prefix(backup_id)
    staged = Path(tempfile.mkdtemp(prefix=".catalog-restore-", dir=parent))
    try:
        manifest = store.get(base + MANIFEST)
        if sha256(manifest) != manifest_sha:
            raise ValueError("manifest changed during restore")
        publish(staged / "catalog" / MANIFEST, manifest)
        for name in MANIFEST_MEMBERS:
            data = read_verified_member(store, base, name, inventory["members"][name])
            publish(staged / "catalog" / name, data)
        for checksum, expected in sorted(inventory["objects"].items()):
            data = read_verified_member(store, base, object_member(checksum), expected)
            publish(staged / "catalog" / "objects" / checksum, data)
            check_blob(staged, checksum, expected["bytes"])
        publish(
            staged / RESTORE_STATE,
            restore_state_bytes(backup_id, manifest_sha, token, "pending"),
        )
    except BaseException:
        shutil.rmtree(staged, ignore_errors=True)
        raise
    return staged


def publish_tree(staged: Path, destination: Path) -> None:
    """Atomically move the staged tree into a freshly reserved destination."""
    destination.mkdir()  # exclusive: fails if the name appeared meanwhile
    try:
        os.replace(staged, destination)
    except OSError:
        destination.rmdir()
        raise


def apply_database(connection, specification, catalog, destination, hook) -> None:
    """Insert every row and reconcile against the published tree; commit last."""
    transaction = connection.begin()
    try:
        connection.execute(text("SET LOCAL TIME ZONE 'UTC'"))
        reflected = tables(connection)
        for name in CATALOG_RESTORE_ORDER:
            for row in catalog[name]:
                restore_row(connection, reflected[name], row)
        report = reconcile_connection(connection, destination, specification)
        if not report["ok"]:
            raise ValueError("restored catalog does not reconcile")
        hook("before_database_commit")
    except BaseException:
        if transaction.is_active:
            transaction.rollback()
        raise
    transaction.commit()


def finalize_restore(destination, backup_id, manifest_sha, token) -> None:
    pending = destination / (RESTORE_STATE + ".next")
    pending.unlink(missing_ok=True)
    publish(pending, restore_state_bytes(backup_id, manifest_sha, token, "complete"))
    os.replace(pending, destination / RESTORE_STATE)


def discard_restore(destination: Path, token: str) -> None:
    """Remove only a destination this restore created and has not committed."""
    state = read_restore_state(destination)
    if state and state["token"] == token and state["state"] == "pending":
        shutil.rmtree(destination)


def verify_destination(store, backup_id, destination, inventory) -> None:
    """A pending destination must hold exactly the verified backup bytes."""
    base = prefix(backup_id)
    for name in MANIFEST_MEMBERS:
        data = read_verified_member(store, base, name, inventory["members"][name])
        if (destination / "catalog" / name).read_bytes() != data:
            raise ValueError(f"restore destination differs from backup: {name}")
    for checksum, expected in inventory["objects"].items():
        check_blob(destination, checksum, expected["bytes"])


def resume_restore(
    connection,
    store,
    backup_id,
    destination,
    manifest_sha,
    specification,
    catalog,
    inventory,
    state,
    hook,
) -> None:
    if state["backup_id"] != backup_id or state["manifest_sha256"] != manifest_sha:
        raise ValueError("destination holds a different catalog restore")
    if state["state"] == "complete":
        raise FileExistsError(f"catalog already restored at {destination}")
    if state["state"] != "pending":
        raise ValueError("unsupported restore state")

    verify_destination(store, backup_id, destination, inventory)
    with connection.begin():
        committed = version_present(connection, specification["version_id"])
        if committed:
            report = reconcile_connection(connection, destination, specification)
            if not report["ok"]:
                raise ValueError("restored catalog does not reconcile")
    if not committed:
        apply_database(connection, specification, catalog, destination, hook)
    finalize_restore(destination, backup_id, manifest_sha, state["token"])


def restore_catalog(
    engine,
    store,
    backup_id: str,
    destination: Path,
    hook=None,
) -> str:
    """Restore a verified backup into a fresh destination and database.

    Rerunning with the same arguments finishes an interrupted restore. The
    optional hook receives stage names so tests can inject failures.
    """
    if hook is None:

        def hook(stage):
            return None

    destination = Path(destination)
    manifest_sha, specification, catalog, _, inventory = read_verified_bundle(
        store, backup_id
    )
    version_id = specification["version_id"]

    with writer(engine) as connection:
        if destination.is_symlink():
            raise FileExistsError(destination)
        if destination.exists():
            state = read_restore_state(destination)
            if state is None:
                raise FileExistsError(destination)
            resume_restore(
                connection,
                store,
                backup_id,
                destination,
                manifest_sha,
                specification,
                catalog,
                inventory,
                state,
                hook,
            )
            return manifest_sha

        with connection.begin():
            if version_present(connection, version_id):
                raise ValueError("catalog restore destination already contains version")

        destination.parent.mkdir(parents=True, exist_ok=True)
        token = secrets.token_hex(16)
        staged = stage_restore(
            store, backup_id, destination.parent, manifest_sha, inventory, token
        )
        try:
            hook("after_staging")
            hook("before_publication")
            publish_tree(staged, destination)
        except BaseException:
            shutil.rmtree(staged, ignore_errors=True)
            raise

        try:
            hook("after_publication")
            apply_database(connection, specification, catalog, destination, hook)
        except Exception as exc:
            outcome = database_outcome(engine, version_id)
            if outcome is False:
                discard_restore(destination, token)
                raise
            raise RestoreIncomplete(
                f"database commit state is {'committed' if outcome else 'unknown'}; "
                f"rerun the same restore to resume {destination}"
            ) from exc

        try:
            hook("after_database_commit")
            finalize_restore(destination, backup_id, manifest_sha, token)
        except Exception as exc:
            raise RestoreIncomplete(
                "database committed but the restore was not finalized; "
                f"rerun the same restore to resume {destination}"
            ) from exc

    return manifest_sha
