"""Annotation quality tests using self-created images and XML."""

import io
import json

import pytest
from PIL import Image
from typer.testing import CliRunner

from worker.cli import app
from worker.inventory import canonical_json, inventory
from worker.review import check_review, make_packet
from worker.validation import (
    CLASSES,
    apply_revision,
    audit,
    decode_image,
    from_yolo,
    inspect_pair,
    make_revision,
    sha256,
    source_box,
    split_findings,
    to_source,
    to_yolo,
    write_bundle,
)

PIXELS = b"P5\n2 2\n255\n" + bytes([0, 32, 128, 240])


def xml(name="crazing", filename="a.pgm", box=("1", "1", "2", "2")):
    x1, y1, x2, y2 = box
    return f"""<annotation>
<filename>{filename}</filename>
<size><width>2</width><height>2</height><depth>1</depth></size>
<object><name>{name}</name><bndbox>
<xmin>{x1}</xmin><ymin>{y1}</ymin><xmax>{x2}</xmax><ymax>{y2}</ymax>
</bndbox></object></annotation>""".encode()


def errors(item):
    return {issue["rule"] for issue in item["issues"] if issue["severity"] == "error"}


def inspect(data=PIXELS, annotation=None):
    return inspect_pair(
        data,
        xml() if annotation is None else annotation,
        "IMAGES/a.pgm",
        "one-based-inclusive",
    )


def dataset(tmp_path):
    root = tmp_path / "raw"
    (root / "IMAGES").mkdir(parents=True)
    (root / "ANNOTATIONS").mkdir()
    (root / "IMAGES/a.pgm").write_bytes(PIXELS)
    (root / "ANNOTATIONS/a.xml").write_bytes(xml())
    return root


def baseline(root, tmp_path):
    manifest, _ = inventory(root)
    data = canonical_json(manifest)
    path = tmp_path / "baseline.json"
    path.write_bytes(data)
    return path, sha256(data)


@pytest.mark.parametrize(
    "box",
    [
        ("1", "1", "1", "1"),
        ("1", "1", "200", "200"),
        ("2", "3", "8", "12"),
    ],
)
def test_box_round_trips(box):
    canonical = source_box(box, 200, 200, "one-based-inclusive")
    assert to_source(canonical, "one-based-inclusive") == list(map(float, box))
    assert from_yolo(to_yolo(canonical, 200, 200), 200, 200) == pytest.approx(canonical)


def test_zero_based_round_trip():
    box = source_box(["0", "0", "2", "2"], 2, 2, "zero-based-half-open")
    assert box == [0, 0, 2, 2]
    assert to_source(box, "zero-based-half-open") == box


@pytest.mark.parametrize(
    "data",
    [
        b"broken",
        PIXELS[:-2],
        b"P5\n2000 2000\n255\n",
        b"P5\n0 2\n255\n",
    ],
)
def test_dq01_invalid_images(data):
    assert "DQ01" in errors(inspect(data=data))


def test_dq02_rgb_variant_and_depth_warning():
    image = Image.new("RGB", (2, 2), (10, 10, 10))
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    item = inspect(data=stream.getvalue())
    warnings = {
        issue["rule"] for issue in item["issues"] if issue["severity"] == "warning"
    }
    assert {"DQ02", "DQ06"} <= warnings
    assert item["decoded"]["equal_rgb_channels"]
    assert not errors(item)


@pytest.mark.parametrize(
    "annotation",
    [
        b"<annotation>",
        b"<!DOCTYPE annotation><annotation/>",
        (
            "<!DOCTYPE annotation [<!ENTITY x SYSTEM 'file:///unread'>]>"
            "<annotation>&x;</annotation>"
        ).encode("utf-16"),
        b"<annotation><filename>a.pgm</filename></annotation>",
        xml(filename="different.pgm"),
    ],
)
def test_dq03_bad_annotations(annotation):
    assert "DQ03" in errors(inspect(annotation=annotation))


def test_dq03_missing_and_extensionless_annotations():
    missing = inspect_pair(PIXELS, None, "IMAGES/a.pgm", "one-based-inclusive")
    assert "DQ03" in errors(missing)
    accepted = inspect(annotation=xml(filename="a"))
    assert not errors(accepted)
    assert any(issue["rule"] == "DQ03" for issue in accepted["issues"])


def test_dq04_alias_and_unknown_class():
    alias = inspect(annotation=xml(name="rolled-in_scale"))
    assert alias["boxes"][0][0] == 4
    assert alias["raw_objects"][0]["name"] == "rolled-in_scale"
    assert "DQ04" in errors(inspect(annotation=xml(name="unknown")))


@pytest.mark.parametrize(
    "box",
    [
        ("-1", "1", "2", "2"),
        ("2", "1", "1", "2"),
        ("NaN", "1", "2", "2"),
        ("1", "1", "3", "2"),
    ],
)
def test_dq05_bad_boxes(box):
    assert "DQ05" in errors(inspect(annotation=xml(box=box)))


def test_dq06_dimension_mismatch():
    annotation = xml().replace(b"<width>2</width>", b"<width>3</width>")
    assert "DQ06" in errors(inspect(annotation=annotation))


def test_dq07_conflicting_duplicate_annotations(tmp_path):
    root = dataset(tmp_path)
    (root / "IMAGES/b.pgm").write_bytes(PIXELS)
    (root / "ANNOTATIONS/b.xml").write_bytes(
        xml(filename="b.pgm", box=("1", "1", "1", "1"))
    )
    path, checksum = baseline(root, tmp_path)
    report = audit(root, path, checksum, "one-based-inclusive")
    assert len(report["duplicates"]) == 1
    assert report["duplicates"][0]["conflicting_annotations"]
    assert set(report["quarantine"]) == {"IMAGES/a.pgm", "IMAGES/b.pgm"}


def test_dq08_split_leakage_contract():
    assignments = [
        {"group": "same-content", "split": "train"},
        {"group": "same-content", "split": "test"},
    ]
    assert split_findings(assignments)[0]["rule"] == "DQ08"
    assignments[1]["split"] = "train"
    assert split_findings(assignments) == []


def test_dq09_changed_source_blocks_candidates(tmp_path):
    root = dataset(tmp_path)
    path, checksum = baseline(root, tmp_path)
    (root / "IMAGES/a.pgm").write_bytes(PIXELS[:-1] + b"\x7f")
    report = audit(root, path, checksum, "one-based-inclusive")
    assert any(issue["rule"] == "DQ09" for issue in report["issues"])
    assert report["quarantine"] == ["IMAGES/a.pgm"]


def test_dq10_class_and_brightness_warnings(tmp_path):
    root = dataset(tmp_path)
    path, checksum = baseline(root, tmp_path)
    reference = {
        "class_images": {"0": 2, "1": 1},
        "brightness_mean": 255,
        "brightness_tolerance": 1,
    }
    report = audit(root, path, checksum, "one-based-inclusive", reference=reference)
    findings = [issue for issue in report["issues"] if issue["rule"] == "DQ10"]
    assert len(findings) == 3
    assert all(issue["severity"] == "warning" for issue in findings)
    assert report["quarantine"] == []


def test_corrections_preserve_raw_bytes_and_validate_parent(tmp_path):
    root = dataset(tmp_path)
    original = (root / "ANNOTATIONS/a.xml").read_bytes()
    path, checksum = baseline(root, tmp_path)
    report = audit(root, path, checksum, "one-based-inclusive")
    item = report["items"]["IMAGES/a.pgm"]
    parent = item["annotation_id"]
    revision = make_revision(
        item, [[0, 0, 0, 1, 1]], "Fixture reviewer", "Synthetic correction"
    )

    output = tmp_path / "revision"
    write_bundle(root, output, {"revision.json": canonical_json(revision)})
    with pytest.raises(FileExistsError):
        write_bundle(root, output, {"revision.json": b"replacement"})

    corrected = audit(root, path, checksum, "one-based-inclusive", revisions=[revision])
    current = corrected["items"]["IMAGES/a.pgm"]
    assert current["boxes"] == [[0, 0, 0, 1, 1]]
    assert current["annotation_id"] != parent
    assert current["revision_history"] == [revision]
    assert (root / "ANNOTATIONS/a.xml").read_bytes() == original
    with pytest.raises(ValueError, match="parent"):
        apply_revision(current, revision)


def test_cli_audit_and_repeatability(tmp_path):
    root = dataset(tmp_path)
    path, checksum = baseline(root, tmp_path)
    runner = CliRunner()

    for name in ("first", "second"):
        result = runner.invoke(
            app,
            [
                "validate-dataset",
                "--root",
                str(root),
                "--baseline",
                str(path),
                "--baseline-sha",
                checksum,
                "--coordinates",
                "one-based-inclusive",
                "--output",
                str(tmp_path / name),
            ],
        )
        assert result.exit_code == 0, result.output

    assert (tmp_path / "first/audit.json").read_bytes() == (
        tmp_path / "second/audit.json"
    ).read_bytes()


def test_review_requires_identity_notes_and_coverage(tmp_path):
    root = dataset(tmp_path)
    objects = []
    for name in CLASSES:
        text = xml(name=name).decode()
        objects.append(
            "<object>" + text.split("<object>")[1].split("</object>")[0] + "</object>"
        )
    annotation = (
        "<annotation><filename>a.pgm</filename>"
        "<size><width>2</width><height>2</height><depth>1</depth></size>"
        + "".join(objects)
        + "</annotation>"
    )
    (root / "ANNOTATIONS/a.xml").write_text(annotation, encoding="utf-8")
    path, checksum = baseline(root, tmp_path)
    report = audit(root, path, checksum, "one-based-inclusive")
    audit_path = tmp_path / "audit.json"
    audit_path.write_bytes(canonical_json(report))

    packet = tmp_path / "packet"
    make_packet(root, audit_path, packet, per_class=1)
    with pytest.raises(ValueError):
        check_review(packet, per_class=1)

    review_path = packet / "review.json"
    review = json.loads(review_path.read_bytes())
    review.update(
        {
            "reviewer": "Fixture reviewer",
            "reviewed_at": "2026-11-18T12:00:00+08:00",
            "coordinate_basis": "Synthetic known one-based fixture.",
            "warning_disposition": "Synthetic 2x2 geometry is intentional.",
        }
    )
    for item in review["items"]:
        item["decision"] = "accept"
        item["notes"] = "Checked synthetic labels and border boxes."
    review_path.write_bytes(canonical_json(review))

    receipt = check_review(packet, per_class=1)
    assert set(receipt["reviewed_per_class"].values()) == {1}
    overlay = packet / review["items"][0]["overlay"]
    overlay.write_bytes(b"changed")
    with pytest.raises(ValueError, match="artifact changed"):
        check_review(packet, per_class=1)


def test_decode_single_frame_pgm_and_jpeg():
    pgm = decode_image(PIXELS)
    assert (pgm["width"], pgm["height"]) == (2, 2)
    assert pgm["mode"] == "L"

    stream = io.BytesIO()
    Image.new("RGB", (2, 2), (10, 20, 30)).save(stream, format="JPEG")
    jpeg = decode_image(stream.getvalue())
    assert (jpeg["width"], jpeg["height"]) == (2, 2)
    assert jpeg["mode"] == "RGB"


def test_decode_rejects_real_multiframe_gif():
    stream = io.BytesIO()
    first = Image.new("RGB", (2, 2), "black")
    second = Image.new("RGB", (2, 2), "white")
    first.save(stream, format="GIF", save_all=True, append_images=[second], loop=0)
    data = stream.getvalue()
    with Image.open(io.BytesIO(data)) as image:
        assert image.n_frames == 2, "the fixture must actually contain two frames"
    with pytest.raises(ValueError, match="multiple image frames"):
        decode_image(data)
