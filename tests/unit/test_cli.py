"""Smoke tests for the installed VisionQ CLI."""

import json
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path


def run_cli(directory: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "worker", *args],
        cwd=directory,
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )


def test_info_works_outside_repository(tmp_path: Path) -> None:
    result = run_cli(tmp_path, "info")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["application"] == "visionq"
    assert payload["version"] == version("visionq")
    assert payload["python"].split(".")[:2] == ["3", "11"]
    assert payload["platform"]


def test_help_lists_info_and_catalog_commands(tmp_path: Path) -> None:
    result = run_cli(tmp_path, "--help")

    assert result.returncode == 0, result.stderr
    assert "info" in result.stdout
    assert "catalog-import" in result.stdout
    assert "catalog-restore" in result.stdout


def test_unknown_command_is_rejected(tmp_path: Path) -> None:
    result = run_cli(tmp_path, "not-a-command")

    assert result.returncode == 2
    assert "not-a-command" in result.stderr + result.stdout


def test_catalog_help_lists_commands(tmp_path: Path) -> None:
    result = run_cli(tmp_path, "--help")

    assert result.returncode == 0, result.stderr
    for command in (
        "catalog-import",
        "catalog-resume",
        "catalog-status",
        "catalog-reconcile",
        "catalog-backup",
        "catalog-verify",
        "catalog-restore",
    ):
        assert command in result.stdout


def test_catalog_verify_missing_local_backup(tmp_path: Path) -> None:
    result = run_cli(
        tmp_path,
        "catalog-verify",
        "--backup-id",
        "00000000-0000-0000-0000-000000000001",
        "--local-store",
        str(tmp_path / "missing-store"),
    )

    assert result.returncode == 1
    assert "COMPLETE missing" in result.stderr + result.stdout
