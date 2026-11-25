from __future__ import annotations

import json
import os
import subprocess
import sys
from uuid import uuid4

from catalog_support import build_release

from worker.backup import Directory
from worker.catalog import ingest
from worker.catalog_backup import (
    backup_catalog,
    prefix,
    read_restore_state,
)


def url_of(engine):
    return engine.url.render_as_string(hide_password=False)


def run_cli(workdir, url, *args, drop=()):
    environment = {
        key: value
        for key, value in os.environ.items()
        if key not in ("VISIONQ_DATABASE_URL", "POSTGRES_PASSWORD", *drop)
    }
    if url is not None:
        environment["VISIONQ_DATABASE_URL"] = url
    workdir.mkdir(exist_ok=True)
    return subprocess.run(
        [sys.executable, "-m", "worker", *args],
        cwd=workdir,
        env=environment,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def package_arguments(tmp_path, package, dataset_name=None):
    version = package.rows["dataset_versions"][0]
    return [
        "--source",
        str(tmp_path / "source"),
        "--baseline",
        str(tmp_path / "baseline.json"),
        "--packet",
        str(tmp_path / "packet"),
        "--release",
        str(tmp_path / "release"),
        "--release-sha",
        version["release_manifest_sha256"],
        "--dataset-name",
        dataset_name or version["dataset_name"],
        "--version",
        "1",
    ]


def test_catalog_commands_end_to_end_from_outside_the_repository(
    postgres_engine, restore_engine, tmp_path
):
    package, _ = build_release(tmp_path, "synthetic-t4-cli", 1)
    source_url = url_of(postgres_engine)
    restore_url = url_of(restore_engine)
    secrets = (postgres_engine.url.password, restore_engine.url.password)
    work = tmp_path / "elsewhere"
    root = tmp_path / "artifacts"
    store = tmp_path / "store"
    arguments = package_arguments(tmp_path, package)

    def cli(url, *args, **kwargs):
        result = run_cli(work, url, *args, **kwargs)
        assert not any(secret in result.stdout + result.stderr for secret in secrets)
        return result

    imported = cli(
        source_url, "catalog-import", *arguments, "--artifact-root", str(root)
    )
    assert imported.returncode == 0, imported.stderr
    assert json.loads(imported.stdout)["ok"] is True

    repeated = cli(
        source_url, "catalog-import", *arguments, "--artifact-root", str(root)
    )
    assert repeated.returncode == 0, repeated.stderr
    assert json.loads(repeated.stdout) == json.loads(imported.stdout)

    status = cli(source_url, "catalog-status", "--run-id", package.run_id)
    assert status.returncode == 0, status.stderr
    payload = json.loads(status.stdout)
    assert payload["operation"]["status"] == "succeeded"
    assert payload["items"]["succeeded"] == len(package.unit_artifacts)

    unknown = cli(source_url, "catalog-status", "--run-id", str(uuid4()))
    assert unknown.returncode == 1
    assert "unknown ingestion operation" in unknown.stderr

    wrong_run = cli(
        source_url,
        "catalog-resume",
        *arguments,
        "--artifact-root",
        str(root),
        "--run-id",
        str(uuid4()),
    )
    assert wrong_run.returncode == 1
    assert "does not match" in wrong_run.stderr

    reconcile_arguments = (
        "catalog-reconcile",
        *arguments,
        "--artifact-root",
        str(root),
    )
    clean = cli(source_url, *reconcile_arguments)
    assert clean.returncode == 0, clean.stderr
    assert "ok=true" in clean.stdout
    assert cli(source_url, *reconcile_arguments).stdout == clean.stdout

    checksum = sorted(package.blobs)[0]
    artifact = root / "catalog" / "objects" / checksum
    original = artifact.read_bytes()
    artifact.unlink()
    broken = cli(source_url, *reconcile_arguments)
    assert broken.returncode == 1
    assert f"missing_artifact catalog_artifacts {checksum}" in broken.stdout
    artifact.write_bytes(original)

    backup_id = str(uuid4())
    backup_arguments = (
        "catalog-backup",
        *arguments,
        "--artifact-root",
        str(root),
        "--local-store",
        str(store),
        "--backup-id",
        backup_id,
    )
    backup = cli(source_url, *backup_arguments)
    assert backup.returncode == 0, backup.stderr
    manifest_sha = json.loads(backup.stdout)["manifest_sha256"]

    again = cli(source_url, *backup_arguments)
    assert again.returncode == 1
    assert "already exists" in again.stderr

    verify = cli(
        None,
        "catalog-verify",
        "--backup-id",
        backup_id,
        "--local-store",
        str(store),
    )
    assert verify.returncode == 0, verify.stderr
    assert json.loads(verify.stdout)["verified"] is True

    restored = tmp_path / "restored"
    restore_arguments = (
        "catalog-restore",
        "--backup-id",
        backup_id,
        "--local-store",
        str(store),
        "--destination",
        str(restored),
    )
    refused = cli(
        "postgresql+psycopg://u:p@db.example.invalid:5432/x", *restore_arguments
    )
    assert refused.returncode == 1
    assert "loopback" in refused.stderr
    assert not restored.exists()

    done = cli(restore_url, *restore_arguments)
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout)["manifest_sha256"] == manifest_sha
    assert read_restore_state(restored)["state"] == "complete"

    verified = cli(
        restore_url,
        "catalog-reconcile",
        *arguments,
        "--artifact-root",
        str(restored),
    )
    assert verified.returncode == 0, verified.stderr
    assert "ok=true" in verified.stdout

    twice = cli(restore_url, *restore_arguments)
    assert twice.returncode == 1
    assert "already" in twice.stderr


def test_catalog_commands_reject_bad_input_with_actionable_errors(
    postgres_engine, tmp_path, monkeypatch
):
    package, _ = build_release(tmp_path, "synthetic-t4-cli-errors", 1)
    source_url = url_of(postgres_engine)
    work = tmp_path / "elsewhere"
    store = tmp_path / "store"
    arguments = package_arguments(tmp_path, package)

    real = run_cli(
        work,
        source_url,
        "catalog-import",
        *package_arguments(tmp_path, package, dataset_name="neu-det"),
        "--artifact-root",
        str(tmp_path / "artifacts"),
    )
    assert real.returncode == 1
    assert "real ingestion is disabled" in real.stderr
    assert not (tmp_path / "artifacts").exists()

    unconfigured = run_cli(
        work,
        None,
        "catalog-status",
        "--run-id",
        str(uuid4()),
    )
    assert unconfigured.returncode == 1
    assert "POSTGRES_PASSWORD" in unconfigured.stderr
    assert "Traceback" not in unconfigured.stderr

    bad_id = run_cli(
        work,
        None,
        "catalog-verify",
        "--backup-id",
        "not-a-uuid",
        "--local-store",
        str(store),
    )
    assert bad_id.returncode == 1
    assert "canonical UUID" in bad_id.stderr

    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("TERM", "xterm-256color")
    remote = run_cli(
        work,
        source_url,
        "catalog-backup",
        *arguments,
        "--artifact-root",
        str(tmp_path / "artifacts"),
        "--backup-id",
        str(uuid4()),
    )
    assert remote.returncode == 2
    assert "--local-store" in remote.stderr


def test_cli_verify_reports_a_corrupt_backup(postgres_engine, tmp_path):
    package, _ = build_release(tmp_path, "synthetic-t4-cli-corrupt", 1)
    root = tmp_path / "artifacts"
    ingest(postgres_engine, root, package)

    store = Directory(tmp_path / "store")
    backup_id = str(uuid4())
    backup_catalog(postgres_engine, root, store, backup_id, package)
    (store.root / prefix(backup_id) / "catalog.json").write_bytes(b"[]")

    result = run_cli(
        tmp_path / "elsewhere",
        None,
        "catalog-verify",
        "--backup-id",
        backup_id,
        "--local-store",
        str(store.root),
    )
    assert result.returncode == 1
    assert "checksum mismatch: catalog.json" in result.stderr
