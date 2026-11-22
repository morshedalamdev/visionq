import json
import shutil
from pathlib import Path

import pytest

from worker.catalog_input import (
    FROZEN_AUDIT_SHA256,
    FROZEN_RELEASE_SHA256,
    FROZEN_REVIEW_SHA256,
    FROZEN_SOURCE_SHA256,
    load_package,
)
from worker.validation import CLASSES, sha256

REPO = Path(__file__).resolve().parents[2]
FROZEN = REPO / "tests/fixtures/m2t3-development/synthetic-only"


def frozen_arguments():
    return {
        "source": FROZEN / "raw",
        "baseline": FROZEN / "baseline.json",
        "packet": FROZEN / "packet",
        "release": FROZEN / "export-a",
        "release_sha256": FROZEN_RELEASE_SHA256,
        "dataset_name": "synthetic-m3t3-frozen-unit",
        "version": 1,
    }


def frozen_copy(tmp_path):
    source = tmp_path / "package"
    shutil.copytree(FROZEN, source)
    return {
        **frozen_arguments(),
        "source": source / "raw",
        "baseline": source / "baseline.json",
        "packet": source / "packet",
        "release": source / "export-a",
    }


def test_exact_frozen_package_has_expected_identity_and_membership():
    package = load_package(**frozen_arguments())
    version = package.rows["dataset_versions"][0]

    assert version["source_manifest_sha256"] == FROZEN_SOURCE_SHA256
    assert version["release_manifest_sha256"] == FROZEN_RELEASE_SHA256
    assert sha256((FROZEN / "packet/audit.json").read_bytes()) == FROZEN_AUDIT_SHA256
    assert sha256((FROZEN / "packet/review.json").read_bytes()) == FROZEN_REVIEW_SHA256
    assert len(package.rows["dataset_items"]) == 24
    splits = {
        split: sum(item["split"] == split for item in package.rows["dataset_items"])
        for split in ("train", "validation", "test")
    }
    assert splits == {"train": 17, "validation": 4, "test": 3}
    assert {row["class_id"] for row in package.rows["annotations"]} == set(
        range(len(CLASSES))
    )


def test_frozen_raw_png_xml_artifacts_are_registered_under_verified_hashes():
    package = load_package(**frozen_arguments())
    baseline = json.loads((FROZEN / "baseline.json").read_bytes())

    for row in baseline:
        expected = (FROZEN / "raw" / row["path"]).read_bytes()
        assert package.blobs[row["sha256"]] == expected
        assert sha256(package.blobs[row["sha256"]]) == row["sha256"]


@pytest.mark.parametrize(
    ("member", "change"),
    [
        ("source", b"altered-source"),
        ("baseline", b" "),
        ("review", b" "),
        ("release", b" "),
    ],
)
def test_frozen_tampering_is_rejected_without_database_access(tmp_path, member, change):
    arguments = frozen_copy(tmp_path)
    if member == "source":
        target = arguments["source"] / "IMAGES/a0.png"
    elif member == "baseline":
        target = arguments["baseline"]
    elif member == "review":
        target = arguments["packet"] / "review.json"
    else:
        target = arguments["release"] / "release.json"
    target.write_bytes(target.read_bytes() + change)

    with pytest.raises(ValueError):
        load_package(**arguments)
