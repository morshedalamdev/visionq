"""Inventory tests using self-created data only."""

import hashlib
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from worker.cli import app
from worker.inventory import inventory, publish_inventory

PIXELS = b"P5\n2 2\n255\n" + bytes([0, 32, 128, 240])
XML = b"""<annotation>
<folder>fixture</folder>
<filename>a.pgm</filename>
<source><database>fixture-only</database></source>
<size><width>2</width><height>2</height><depth>1</depth></size>
<object><name>fixture</name><bndbox>
<xmin>1</xmin><ymin>1</ymin><xmax>2</xmax><ymax>2</ymax>
</bndbox></object>
<object><name>fixture</name><bndbox>
<xmin>1</xmin><ymin>1</ymin><xmax>2</xmax><ymax>2</ymax>
</bndbox></object>
<object><name>rolled-in_scale</name><bndbox>
<xmin>1</xmin><ymin>1</ymin><xmax>2</xmax><ymax>2</ymax>
</bndbox></object>
</annotation>
"""


@pytest.fixture
def raw(tmp_path: Path) -> Path:
    root = tmp_path / "NEU-DET"
    for directory in ("IMAGES", "ANNOTATIONS", "ImageSets"):
        (root / directory).mkdir(parents=True)

    (root / "IMAGES/a.pgm").write_bytes(PIXELS)
    (root / "ANNOTATIONS/a.xml").write_bytes(XML)
    (root / "NOTICE.txt").write_text(
        "Self-created VisionQ test fixture.\n", encoding="utf-8"
    )
    (root / "ImageSets/test.txt").write_text("a\n", encoding="utf-8")
    (root / ".DS_Store").write_bytes(b"synthetic hidden metadata")

    excluded = tmp_path / "NEU-CLS"
    excluded.mkdir()
    (excluded / "excluded.pgm").write_bytes(PIXELS)
    return root


def source_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_repeatable_inventory_preserves_all_source_bytes(raw, tmp_path):
    before = source_bytes(raw)
    first = tmp_path / "first"
    second = tmp_path / "second"

    report = publish_inventory(raw, first)
    publish_inventory(raw, second)

    assert source_bytes(raw) == before
    for name in ("manifest.json", "report.json", "facts.md"):
        assert (first / name).read_bytes() == (second / name).read_bytes()

    manifest_bytes = (first / "manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    assert [row["path"] for row in manifest] == sorted(before)
    assert report["manifest_sha256"] == hashlib.sha256(manifest_bytes).hexdigest()

    for row in manifest:
        original = before[row["path"]]
        assert row["bytes"] == len(original)
        assert row["sha256"] == hashlib.sha256(original).hexdigest()

    assert report["counts"]["regular_files"] == 5
    assert report["counts"]["image_candidates"] == 1
    assert report["counts"]["xml_files"] == 1
    assert report["counts"]["other_files"] == 3
    assert report["counts"]["stem_pairs"] == 1
    assert report["counts"]["xml_objects"] == 3
    assert report["counts"]["xmls_with_multiple_labels"] == 1
    assert report["object_name_counts"] == {
        "fixture": 2,
        "rolled-in_scale": 1,
    }
    assert report["xml_files_per_label"] == {
        "fixture": 1,
        "rolled-in_scale": 1,
    }
    assert report["xml_metadata"]["ANNOTATIONS/a.xml"]["source_fields"] == [
        {"tag": "database", "text": "fixture-only"}
    ]


def test_changed_fixture_bytes_change_manifest_digest(raw):
    before_manifest, before_report = inventory(raw)
    image = raw / "IMAGES/a.pgm"
    image.write_bytes(PIXELS[:-1] + b"\x7f")
    after_manifest, after_report = inventory(raw)

    assert before_report["counts"] == after_report["counts"]
    assert before_report["manifest_sha256"] != after_report["manifest_sha256"]

    before = {row["path"]: row["sha256"] for row in before_manifest}
    after = {row["path"]: row["sha256"] for row in after_manifest}
    changed = {name for name in before if before[name] != after[name]}
    assert changed == {"IMAGES/a.pgm"}


def test_unmatched_inputs_are_reported(raw):
    (raw / "IMAGES/lonely.pgm").write_bytes(PIXELS)
    (raw / "ANNOTATIONS/orphan.xml").write_bytes(XML)

    _, report = inventory(raw)

    assert report["counts"]["stem_pairs"] == 1
    assert report["images_without_xml"] == ["IMAGES/lonely.pgm"]
    assert report["xml_without_images"] == ["ANNOTATIONS/orphan.xml"]


def test_extensionless_xml_filename_is_preserved_and_reported(raw):
    path = raw / "ANNOTATIONS/a.xml"
    changed = XML.replace(b"<filename>a.pgm</filename>", b"<filename>a</filename>")
    path.write_bytes(changed)

    _, report = inventory(raw)

    assert path.read_bytes() == changed
    assert report["counts"]["stem_pairs"] == 1
    assert report["filename_mismatches"] == [
        {
            "xml": "ANNOTATIONS/a.xml",
            "declared": "a",
            "paired_image": "IMAGES/a.pgm",
        }
    ]


def test_ambiguous_stem_is_reported_without_selecting_an_image(raw):
    ppm = b"P6\n2 2\n255\n" + bytes(range(12))
    (raw / "IMAGES/a.ppm").write_bytes(ppm)

    _, report = inventory(raw)

    assert report["counts"]["image_candidates"] == 2
    assert report["counts"]["stem_pairs"] == 0
    assert report["ambiguous_stems"] == [
        {
            "stem": "a",
            "images": ["IMAGES/a.pgm", "IMAGES/a.ppm"],
            "xml": ["ANNOTATIONS/a.xml"],
        }
    ]


@pytest.mark.parametrize(
    "payload",
    [
        b"<annotation>",
        b"<unexpected/>",
        b"<!DOCTYPE annotation><annotation/>",
        "<!DOCTYPE annotation><annotation/>".encode("utf-16"),
    ],
)
def test_xml_inspection_errors_retain_original_file_evidence(raw, payload):
    path = raw / "ANNOTATIONS/a.xml"
    path.write_bytes(payload)

    manifest, report = inventory(raw)

    assert report["counts"]["xml_inspection_errors"] == 1
    assert report["xml_errors"][0]["path"] == "ANNOTATIONS/a.xml"
    row = next(row for row in manifest if row["path"] == "ANNOTATIONS/a.xml")
    assert row["sha256"] == hashlib.sha256(payload).hexdigest()
    assert path.read_bytes() == payload


def test_xml_inspection_limit_is_reported(raw, monkeypatch):
    monkeypatch.setattr("worker.inventory.XML_LIMIT", 16)

    _, report = inventory(raw)

    assert report["counts"]["xml_inspection_errors"] == 1
    assert "inspection limit" in report["xml_errors"][0]["error"]


def test_source_symlink_is_rejected(raw, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("fixture", encoding="utf-8")
    (raw / "linked.txt").symlink_to(outside)

    with pytest.raises(ValueError, match="symlink"):
        inventory(raw)


def test_outputs_require_a_fresh_directory_outside_source(raw, tmp_path):
    before = source_bytes(raw)
    with pytest.raises(ValueError, match="outside"):
        publish_inventory(raw, raw / "generated")

    output = tmp_path / "evidence"
    publish_inventory(raw, output)
    saved = source_bytes(output)

    with pytest.raises(FileExistsError, match="already exists"):
        publish_inventory(raw, output)

    assert source_bytes(raw) == before
    assert source_bytes(output) == saved


def test_cli_inventory_and_error_exit_codes(raw, tmp_path):
    runner = CliRunner()
    output = tmp_path / "cli-output"
    arguments = ["inventory", "--root", str(raw), "--output", str(output)]

    result = runner.invoke(app, arguments)
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["counts"]["stem_pairs"] == 1
    assert (output / "manifest.json").is_file()

    repeated = runner.invoke(app, arguments)
    assert repeated.exit_code == 1
    assert "already exists" in repeated.output

    missing = runner.invoke(
        app,
        [
            "inventory",
            "--root",
            str(tmp_path / "missing"),
            "--output",
            str(tmp_path / "unused"),
        ],
    )
    assert missing.exit_code == 1
    assert not (tmp_path / "unused").exists()
