"""Self-created fixtures only; no real annotation approvals."""

import io
import json
import random

import pytest
from PIL import Image

from worker.inventory import canonical_json, inventory
from worker.preparation import (
    assign_groups,
    exact_groups,
    export,
    letterbox,
    prepare,
    transform_box,
)
from worker.review import make_packet
from worker.validation import CLASSES, audit, from_yolo, sha256, to_yolo


@pytest.fixture
def prepared(tmp_path):
    root = tmp_path / "raw"
    (root / "IMAGES").mkdir(parents=True)
    (root / "ANNOTATIONS").mkdir()
    rng = random.Random(81)
    for i in range(24):
        image = Image.frombytes("L", (16, 16), rng.randbytes(256))
        stream = io.BytesIO()
        image.save(stream, format="PNG")
        (root / f"IMAGES/a{i}.png").write_bytes(stream.getvalue())
        objects = "".join(
            f"<object><name>{name}</name><bndbox><xmin>1</xmin>"
            "<ymin>1</ymin><xmax>16</xmax><ymax>16</ymax>"
            "</bndbox></object>"
            for name in CLASSES
        )
        (root / f"ANNOTATIONS/a{i}.xml").write_text(
            f"<annotation><folder>synthetic</folder><filename>a{i}.png</filename>"
            "<size><width>16</width><height>16</height><depth>1</depth></size>"
            f"{objects}</annotation>"
        )
    manifest, _ = inventory(root)
    baseline = tmp_path / "baseline.json"
    baseline.write_bytes(canonical_json(manifest))
    report = audit(root, baseline, sha256(baseline.read_bytes()), "one-based-inclusive")
    report_path = tmp_path / "audit.json"
    report_path.write_bytes(canonical_json(report))
    packet = tmp_path / "packet"
    make_packet(root, report_path, packet)
    review_path = packet / "review.json"
    review = json.loads(review_path.read_bytes())
    review.update(
        reviewer="Synthetic fixture",
        reviewed_at="2026-11-18T12:00:00+08:00",
        coordinate_basis="Known fixture",
        warning_disposition="Intentional 16px",
    )
    for item in review["items"]:
        item.update(decision="accept", notes="Synthetic known boxes")
    review_path.write_bytes(canonical_json(review))
    return root, packet


def test_transitive_groups_and_split_determinism():
    items = {
        "a": {"image_sha256": "1", "pixel_sha256": "x"},
        "b": {"image_sha256": "2", "pixel_sha256": "x"},
        "c": {"image_sha256": "2", "pixel_sha256": "y"},
    }
    assert exact_groups(items) == [["a", "b", "c"]]
    groups = [
        {"group_id": str(i), "aliases": [str(i)], "categories": ["cr"]}
        for i in range(20)
    ]
    assert assign_groups(groups) == assign_groups(list(reversed(groups)))
    assignments = assign_groups(groups)
    assert list(assignments.values()).count("train") == 14
    assert list(assignments.values()).count("validation") == 3
    assert list(assignments.values()).count("test") == 3
    with pytest.raises(ValueError, match="crosses"):
        assign_groups(
            [{"group_id": "x", "aliases": ["a", "b"], "categories": ["cr"]}],
            {"a": "train", "b": "test"},
        )


@pytest.mark.parametrize("box", [[0, 0, 1, 1], [0, 0, 200, 100], [199, 99, 200, 100]])
def test_geometry(box):
    transform = letterbox(200, 100)
    assert transform["padding"] == [0, 80]
    assert transform_box(
        transform_box(box, transform), transform, inverse=True
    ) == pytest.approx(box)
    assert from_yolo(to_yolo(box, 200, 100), 200, 100) == pytest.approx(box)


def test_plan_quarantine_and_multilabel(prepared):
    root, packet = prepared
    before = prepare(root, packet)
    assert before == prepare(root, packet)
    assert all(all(s["boxes_per_class"].values()) for s in before["stats"].values())
    review_path = packet / "review.json"
    review = json.loads(review_path.read_bytes())
    path = review["items"][0]["image"]
    review["items"][0]["decision"] = "quarantine"
    review_path.write_bytes(canonical_json(review))
    after = prepare(root, packet)
    assert path in after["excluded"]
    assert not any(path in r["aliases"] for r in after["records"])


def test_export_repeatability_and_tampering(prepared, tmp_path):
    root, packet = prepared
    plan = prepare(root, packet)
    assert not plan["near_candidates"]
    path = tmp_path / "plan.json"
    path.write_bytes(canonical_json(plan))
    checksum = sha256(path.read_bytes())
    for name in ("first", "second"):
        export(root, packet, path, checksum, tmp_path / name)
    files = [
        p.relative_to(tmp_path / "first")
        for p in (tmp_path / "first").rglob("*")
        if p.is_file()
    ]
    assert all(
        (tmp_path / "first" / p).read_bytes() == (tmp_path / "second" / p).read_bytes()
        for p in files
    )
    config = (tmp_path / "first/data.yaml").read_text()
    assert "val: images/validation" in config and "5: scratches" in config
    for p in (tmp_path / "first/images").rglob("*.png"):
        with Image.open(p) as image:
            assert image.mode == "RGB" and image.size == (16, 16)
            assert all(r == g == b for r, g, b in image.get_flattened_data())
    with pytest.raises(ValueError, match="checksum"):
        export(root, packet, path, "0" * 64, tmp_path / "bad")
    (root / plan["records"][0]["source"]).write_bytes(b"changed")
    with pytest.raises(ValueError, match="manifest"):
        prepare(root, packet)


def test_pending_review_blocks_export(prepared, tmp_path):
    root, packet = prepared
    review_path = packet / "review.json"
    review = json.loads(review_path.read_bytes())
    review["items"][0]["decision"] = "pending"
    review_path.write_bytes(canonical_json(review))
    path = tmp_path / "plan.json"
    path.write_bytes(canonical_json(prepare(root, packet)))
    with pytest.raises(ValueError, match="pending"):
        export(root, packet, path, sha256(path.read_bytes()), tmp_path / "blocked")
    assert not (tmp_path / "blocked").exists()


def test_export_integrity(prepared, tmp_path):
    from worker.preparation import verify_export

    root, packet = prepared
    path = tmp_path / "plan.json"
    path.write_bytes(canonical_json(prepare(root, packet)))
    output = tmp_path / "export"
    result = export(root, packet, path, sha256(path.read_bytes()), output)
    assert verify_export(output, result["manifest_sha256"])["verified_files"] == 50
    label = next((output / "labels").rglob("*.txt"))
    label.write_text("changed")
    with pytest.raises(ValueError, match="artifact checksum"):
        verify_export(output, result["manifest_sha256"])


def test_official_test_membership_preserved(prepared, tmp_path):
    root, packet = prepared
    source = json.loads((packet / "audit.json").read_bytes())
    membership = {
        p: "test" if i < 4 else "train" for i, p in enumerate(sorted(source["items"]))
    }
    official = tmp_path / "official.json"
    official.write_bytes(
        canonical_json(
            {
                "verified_by": "Fixture",
                "evidence": "Synthetic list",
                "membership": membership,
            }
        )
    )
    plan = prepare(root, packet, official)
    assert {r["source"] for r in plan["records"] if r["split"] == "test"} == {
        p for p, s in membership.items() if s == "test"
    }


def test_near_candidates_are_not_silently_merged(prepared, tmp_path, monkeypatch):
    monkeypatch.setattr("worker.preparation.dhash", lambda data: 0)
    root, packet = prepared
    plan = prepare(root, packet)
    assert len(plan["records"]) == 24
    assert len(plan["near_candidates"]) == 276
    path = tmp_path / "plan.json"
    path.write_bytes(canonical_json(plan))
    digest = sha256(path.read_bytes())
    with pytest.raises(ValueError, match="near-duplicate review"):
        export(root, packet, path, digest, tmp_path / "blocked")
    with pytest.raises(ValueError, match="membership"):
        export(
            root,
            packet,
            path,
            digest,
            tmp_path / "blocked",
            {"plan_sha256": digest, "reviewer": "Fixture", "items": []},
        )
