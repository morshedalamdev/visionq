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


def test_help_lists_info_command(tmp_path: Path) -> None:
    result = run_cli(tmp_path, "--help")

    assert result.returncode == 0, result.stderr
    assert "info" in result.stdout


def test_unknown_command_is_rejected(tmp_path: Path) -> None:
    result = run_cli(tmp_path, "not-a-command")

    assert result.returncode == 2
    assert "not-a-command" in result.stderr + result.stdout
