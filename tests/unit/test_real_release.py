"""Pinned admission and private-local rights boundaries; no fake real acceptance."""

from types import SimpleNamespace

import pytest

from worker.catalog_backup import backup_catalog, rights_for_specification
from worker.real_release import (
    RELEASE_SHA,
    SOURCE_SHA,
    admit_identity,
    validate_real_release,
)


def test_real_admission_requires_exact_pins_and_locations(tmp_path):
    auth = tmp_path / "auth.json"
    admit_identity("NEU-DET", 1, RELEASE_SHA, SOURCE_SHA, auth)
    for name, version, release, source, evidence in [
        ("neu-det", 1, RELEASE_SHA, SOURCE_SHA, auth),
        ("NEU-DET", 2, RELEASE_SHA, SOURCE_SHA, auth),
        ("NEU-DET", 1, "0" * 64, SOURCE_SHA, auth),
        ("NEU-DET", 1, RELEASE_SHA, "0" * 64, auth),
        ("NEU-DET", 1, RELEASE_SHA, SOURCE_SHA, None),
    ]:
        with pytest.raises(ValueError, match="disabled"):
            admit_identity(name, version, release, source, evidence)


def test_real_validation_rejects_missing_or_changed_evidence(tmp_path):
    auth = tmp_path / "auth.json"
    with pytest.raises(FileNotFoundError):
        validate_real_release(tmp_path, tmp_path / "baseline", tmp_path, tmp_path, auth)
    auth.write_text(
        '{"component_packet":"missing", "isolation_constraints":"missing", "frozen_membership":"missing"}'
    )
    baseline = tmp_path / "baseline"
    baseline.write_bytes(b"changed")
    with pytest.raises(ValueError, match="baseline"):
        validate_real_release(tmp_path, baseline, tmp_path, tmp_path, auth)


def test_real_backup_rights_deny_cloud_before_any_store_access():
    spec = {
        "rows": {
            "dataset_versions": [
                {
                    "evidence_kind": "released",
                    "dataset_name": "NEU-DET",
                    "version": 1,
                    "release_manifest_sha256": RELEASE_SHA,
                    "source_manifest_sha256": SOURCE_SHA,
                }
            ]
        },
        "artifacts": {
            "a": {
                "categories": [
                    "annotations",
                    "catalog_metadata",
                    "original_images",
                    "generated_images",
                    "source_metadata",
                ]
            }
        },
    }
    rights = rights_for_specification(spec)
    assert rights["cloud_authorized"] is False
    assert all(
        not x["cloud_upload"] and x["local_backup_restore"]
        for x in rights["category_permissions"].values()
    )
    package = SimpleNamespace(specification=lambda: spec)

    class ForbiddenStore:
        def get(self, key):
            pytest.fail("must reject before external access")

    with pytest.raises(ValueError, match="local-directory"):
        backup_catalog(
            None,
            None,
            ForbiddenStore(),
            "00000000-0000-0000-0000-000000000001",
            package,
        )
    spec["rows"]["dataset_versions"][0]["release_manifest_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="rights clearance"):
        rights_for_specification(spec)
