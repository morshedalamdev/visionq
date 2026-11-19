from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from catalog_support import build_release, version_count
from sqlalchemy import text

from worker.backup import Directory
from worker.catalog import ingest
from worker.catalog_backup import (
    RestoreIncomplete,
    backup_catalog,
    prefix,
    read_restore_state,
    restore_catalog,
    restore_row,
    rights_for_package,
    snapshot_catalog,
    verify_catalog_backup,
)
from worker.catalog_store import CatalogBusy, CatalogConflict, tables, writer
from worker.inventory import canonical_json
from worker.reconciliation import reconcile
from worker.validation import sha256


class Crash(BaseException):
    """Simulates process death: ordinary cleanup handlers must not run."""


def inject(stage, error):
    def hook(name):
        if name == stage:
            raise error

    return hook


def backed_up(postgres_engine, tmp_path, name):
    package, _ = build_release(tmp_path, name, 1)
    root = tmp_path / "artifacts"
    ingest(postgres_engine, root, package)
    store = Directory(tmp_path / "catalog-store")
    backup_id = str(uuid4())
    manifest_sha = backup_catalog(postgres_engine, root, store, backup_id, package)
    return package, root, store, backup_id, manifest_sha


def staging_leftovers(tmp_path):
    return list(tmp_path.glob(".catalog-restore-*"))


def assert_restored(restore_engine, postgres_engine, package, destination):
    specification = package.specification()
    assert snapshot_catalog(restore_engine, specification) == snapshot_catalog(
        postgres_engine, specification
    )
    report = reconcile(restore_engine, destination, specification)
    assert report["ok"] is True
    assert report["findings"] == []
    assert report["orphan_artifacts"] == []
    objects = destination / "catalog" / "objects"
    assert {path.name for path in objects.iterdir()} == set(package.blobs)
    for checksum, data in package.blobs.items():
        assert (objects / checksum).read_bytes() == data
    assert read_restore_state(destination)["state"] == "complete"


def test_catalog_backup_and_verification(postgres_engine, tmp_path):
    package, root, store, backup_id, manifest_sha = backed_up(
        postgres_engine, tmp_path, "synthetic-t4-backup"
    )

    assert verify_catalog_backup(store, backup_id) == manifest_sha
    with pytest.raises(FileExistsError):
        backup_catalog(postgres_engine, root, store, backup_id, package)

    released = replace(
        package,
        rows={
            **package.rows,
            "dataset_versions": [
                {**package.rows["dataset_versions"][0], "evidence_kind": "released"}
            ],
        },
    )
    with pytest.raises(ValueError, match="rights clearance"):
        rights_for_package(released)
    with pytest.raises(ValueError, match="canonical"):
        verify_catalog_backup(store, "not-a-uuid")


def test_interrupted_backup_is_invisible_and_cannot_be_reused(
    postgres_engine, tmp_path
):
    package, _ = build_release(tmp_path, "synthetic-t4-backup-crash", 1)
    root = tmp_path / "artifacts"
    ingest(postgres_engine, root, package)

    class Flaky(Directory):
        def put(self, key, data):
            if "/objects/" in key:
                raise OSError("simulated interruption")
            super().put(key, data)

    backup_id = str(uuid4())
    with pytest.raises(OSError, match="simulated interruption"):
        backup_catalog(
            postgres_engine, root, Flaky(tmp_path / "store"), backup_id, package
        )

    store = Directory(tmp_path / "store")
    with pytest.raises(ValueError, match="COMPLETE missing"):
        verify_catalog_backup(store, backup_id)
    with pytest.raises(FileExistsError, match="choose a new backup id"):
        backup_catalog(postgres_engine, root, store, backup_id, package)

    fresh = str(uuid4())
    manifest_sha = backup_catalog(postgres_engine, root, store, fresh, package)
    assert verify_catalog_backup(store, fresh) == manifest_sha


def test_fresh_restore_into_disposable_database(
    postgres_engine, restore_engine, tmp_path
):
    package, _, store, backup_id, manifest_sha = backed_up(
        postgres_engine, tmp_path, "synthetic-t4-fresh-restore"
    )
    version_id = package.specification()["version_id"]
    assert version_count(restore_engine, version_id) == 0

    restored = tmp_path / "restored"
    assert restore_catalog(restore_engine, store, backup_id, restored) == manifest_sha
    assert_restored(restore_engine, postgres_engine, package, restored)
    assert staging_leftovers(tmp_path) == []

    with pytest.raises(FileExistsError, match="already restored"):
        restore_catalog(restore_engine, store, backup_id, restored)

    second = tmp_path / "second-restore"
    with pytest.raises(ValueError, match="already contains version"):
        restore_catalog(restore_engine, store, backup_id, second)
    assert not second.exists()
    assert staging_leftovers(tmp_path) == []


@pytest.mark.parametrize(
    ("stage", "error"),
    [
        ("after_staging", RuntimeError),
        ("before_publication", OSError),
        ("after_publication", RuntimeError),
        ("before_database_commit", RuntimeError),
    ],
)
def test_failure_before_commit_leaves_nothing_and_retry_succeeds(
    postgres_engine, restore_engine, tmp_path, stage, error
):
    package, _, store, backup_id, manifest_sha = backed_up(
        postgres_engine, tmp_path, "synthetic-t4-restore-window"
    )
    version_id = package.specification()["version_id"]
    restored = tmp_path / "restored"

    with pytest.raises(error, match="injected failure"):
        restore_catalog(
            restore_engine,
            store,
            backup_id,
            restored,
            hook=inject(stage, error("injected failure")),
        )

    assert not restored.exists()
    assert staging_leftovers(tmp_path) == []
    assert version_count(restore_engine, version_id) == 0

    assert restore_catalog(restore_engine, store, backup_id, restored) == manifest_sha
    assert_restored(restore_engine, postgres_engine, package, restored)


def test_rename_failure_removes_the_reservation_and_staging(
    postgres_engine, restore_engine, tmp_path, monkeypatch
):
    package, _, store, backup_id, manifest_sha = backed_up(
        postgres_engine, tmp_path, "synthetic-t4-restore-rename"
    )
    version_id = package.specification()["version_id"]
    restored = tmp_path / "restored"
    real_replace = os.replace

    def failing_replace(source, target):
        if Path(source).name.startswith(".catalog-restore-"):
            raise OSError("injected rename failure")
        return real_replace(source, target)

    with monkeypatch.context() as patch:
        patch.setattr("worker.catalog_backup.os.replace", failing_replace)
        with pytest.raises(OSError, match="injected rename failure"):
            restore_catalog(restore_engine, store, backup_id, restored)

    assert not restored.exists()
    assert staging_leftovers(tmp_path) == []
    assert version_count(restore_engine, version_id) == 0

    assert restore_catalog(restore_engine, store, backup_id, restored) == manifest_sha
    assert_restored(restore_engine, postgres_engine, package, restored)


def test_crash_after_publication_is_detected_and_resumed(
    postgres_engine, restore_engine, tmp_path
):
    package, _, store, backup_id, manifest_sha = backed_up(
        postgres_engine, tmp_path, "synthetic-t4-restore-crash"
    )
    version_id = package.specification()["version_id"]
    restored = tmp_path / "restored"

    with pytest.raises(Crash):
        restore_catalog(
            restore_engine,
            store,
            backup_id,
            restored,
            hook=inject("after_publication", Crash()),
        )

    assert read_restore_state(restored)["state"] == "pending"
    assert version_count(restore_engine, version_id) == 0

    assert restore_catalog(restore_engine, store, backup_id, restored) == manifest_sha
    assert_restored(restore_engine, postgres_engine, package, restored)


def test_failure_after_database_commit_is_finished_by_rerun(
    postgres_engine, restore_engine, tmp_path
):
    package, _, store, backup_id, manifest_sha = backed_up(
        postgres_engine, tmp_path, "synthetic-t4-restore-late"
    )
    version_id = package.specification()["version_id"]
    restored = tmp_path / "restored"

    with pytest.raises(RestoreIncomplete, match="rerun the same restore"):
        restore_catalog(
            restore_engine,
            store,
            backup_id,
            restored,
            hook=inject("after_database_commit", RuntimeError("injected failure")),
        )

    assert version_count(restore_engine, version_id) == 1
    assert read_restore_state(restored)["state"] == "pending"

    other = tmp_path / "other"
    with pytest.raises(ValueError, match="already contains version"):
        restore_catalog(restore_engine, store, backup_id, other)
    assert not other.exists()

    assert restore_catalog(restore_engine, store, backup_id, restored) == manifest_sha
    assert_restored(restore_engine, postgres_engine, package, restored)
    assert version_count(restore_engine, version_id) == 1


def test_resume_refuses_a_tampered_pending_destination(
    postgres_engine, restore_engine, tmp_path
):
    package, _, store, backup_id, _ = backed_up(
        postgres_engine, tmp_path, "synthetic-t4-restore-tamper"
    )
    version_id = package.specification()["version_id"]
    restored = tmp_path / "restored"

    with pytest.raises(Crash):
        restore_catalog(
            restore_engine,
            store,
            backup_id,
            restored,
            hook=inject("after_publication", Crash()),
        )
    victim = restored / "catalog" / "objects" / sorted(package.blobs)[0]
    victim.write_bytes(b"tampered")

    with pytest.raises(ValueError, match="artifact differs"):
        restore_catalog(restore_engine, store, backup_id, restored)

    assert victim.read_bytes() == b"tampered"
    assert read_restore_state(restored)["state"] == "pending"
    assert version_count(restore_engine, version_id) == 0


def forge(base, member=None, rewrite=None, manifest_rewrite=None):
    """Rewrite a backup consistently so only the targeted rule can reject it."""
    manifest_path = base / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    if member is not None:
        data = rewrite((base / member).read_bytes())
        (base / member).write_bytes(data)
        manifest["members"][member] = {"sha256": sha256(data), "bytes": len(data)}
    if manifest_rewrite is not None:
        manifest_rewrite(manifest)
    data = canonical_json(manifest)
    manifest_path.write_bytes(data)
    (base / "COMPLETE").write_bytes(sha256(data).encode("ascii"))


def edit_json(**changes):
    return lambda raw: canonical_json({**json.loads(raw), **changes})


def first_object(base):
    return sorted((base / "objects").iterdir())[0]


DAMAGE = {
    "missing-marker": (lambda b: (b / "COMPLETE").unlink(), "COMPLETE missing"),
    "missing-manifest": (
        lambda b: (b / "manifest.json").unlink(),
        "member missing: manifest.json",
    ),
    "corrupt-manifest": (
        lambda b: (b / "manifest.json").write_bytes(b"{}"),
        "manifest checksum mismatch",
    ),
    "corrupt-member": (
        lambda b: (b / "catalog.json").write_bytes(b"[]"),
        "checksum mismatch: catalog.json",
    ),
    "missing-object": (lambda b: first_object(b).unlink(), "member missing: objects/"),
    "corrupt-object": (
        lambda b: first_object(b).write_bytes(b"tampered"),
        "checksum mismatch: objects/",
    ),
    "released-rights": (
        lambda b: forge(b, "rights.json", edit_json(evidence_kind="released")),
        "requires approved rights",
    ),
    "unsupported-classification": (
        lambda b: forge(b, "rights.json", edit_json(classification="public")),
        "unsupported catalog rights classification",
    ),
    "rights-disagree": (
        lambda b: forge(
            b,
            manifest_rewrite=lambda m: m["rights"].update(classification="public"),
        ),
        "rights manifest differs",
    ),
}


@pytest.mark.parametrize("kind", sorted(DAMAGE))
def test_damaged_or_unauthorized_backups_are_rejected_before_any_write(
    postgres_engine, restore_engine, tmp_path, kind
):
    package, _, store, backup_id, _ = backed_up(
        postgres_engine, tmp_path, "synthetic-t4-damaged"
    )
    damage, message = DAMAGE[kind]
    damage(store.root / prefix(backup_id))
    restored = tmp_path / "restored"

    with pytest.raises(ValueError, match=message):
        verify_catalog_backup(store, backup_id)
    with pytest.raises(ValueError, match=message):
        restore_catalog(restore_engine, store, backup_id, restored)

    assert not restored.exists()
    assert staging_leftovers(tmp_path) == []
    assert version_count(restore_engine, package.specification()["version_id"]) == 0


def test_existing_destinations_are_never_overwritten(
    postgres_engine, restore_engine, tmp_path
):
    package, _, store, backup_id, _ = backed_up(
        postgres_engine, tmp_path, "synthetic-t4-destination"
    )
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    (foreign / "keep.txt").write_text("mine")
    link = tmp_path / "link"
    link.symlink_to(foreign)

    for target in (foreign, link):
        with pytest.raises(FileExistsError):
            restore_catalog(restore_engine, store, backup_id, target)

    assert [path.name for path in foreign.iterdir()] == ["keep.txt"]
    assert version_count(restore_engine, package.specification()["version_id"]) == 0


def test_concurrent_restore_is_rejected_by_the_catalog_lock(
    postgres_engine, restore_engine, tmp_path
):
    package, _, store, backup_id, _ = backed_up(
        postgres_engine, tmp_path, "synthetic-t4-restore-lock"
    )
    restored = tmp_path / "restored"

    with writer(restore_engine):
        with pytest.raises(CatalogBusy):
            restore_catalog(restore_engine, store, backup_id, restored)

    assert not restored.exists()
    assert staging_leftovers(tmp_path) == []
    assert version_count(restore_engine, package.specification()["version_id"]) == 0


def test_restore_row_tolerates_only_creation_time_differences(restore_engine):
    raw = uuid4().hex * 2
    row = {
        "id": str(uuid4()),
        "raw_sha256": raw,
        "pixel_sha256": "a" * 64,
        "width": 16,
        "height": 16,
        "channels": 1,
        "created_at": "2000-01-01 00:00:00+00:00",
    }

    with restore_engine.connect() as connection:
        transaction = connection.begin()
        try:
            assets = tables(connection)["assets"]
            connection.execute(
                text(
                    "INSERT INTO catalog_artifacts (sha256, byte_count) VALUES (:s, 1)"
                ),
                {"s": raw},
            )
            restore_row(connection, assets, row)
            restore_row(
                connection, assets, {**row, "created_at": "2026-11-19 12:00:00+00:00"}
            )
            with pytest.raises(CatalogConflict):
                restore_row(connection, assets, {**row, "pixel_sha256": "b" * 64})
        finally:
            transaction.rollback()
