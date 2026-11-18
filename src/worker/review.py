"""Create deterministic annotation review packets and verify review records."""

import io
import json
import math
from collections import Counter
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw

from worker.inventory import canonical_json, inventory
from worker.validation import (
    CLASSES,
    LIMITS,
    read_source,
    sha256,
    write_bundle,
)


def touches_border(item):
    decoded = item["decoded"]
    if decoded is None:
        return False
    width, height = decoded["width"], decoded["height"]
    return any(
        box[1] == 0 or box[2] == 0 or box[3] == width or box[4] == height
        for box in item["boxes"]
    )


def select_items(report, per_class):
    selected = set(report["quarantine"])
    for class_id in range(len(CLASSES)):
        candidates = [
            item
            for item in report["items"].values()
            if any(box[0] == class_id for box in item["boxes"])
        ]
        candidates.sort(key=lambda item: (not touches_border(item), item["image"]))
        if len(candidates) < per_class:
            raise ValueError(f"insufficient review candidates for class {class_id}")
        selected.update(item["image"] for item in candidates[:per_class])
    return [report["items"][path] for path in sorted(selected)]


def overlay(root, item):
    if item["decoded"] is None:
        canvas = Image.new("RGB", (600, 120), "white")
        ImageDraw.Draw(canvas).text(
            (10, 20),
            "Decode failed. Review audit findings and quarantine.",
            fill="black",
        )
    else:
        data = read_source(root, item["image"], LIMITS["image_bytes"])
        if sha256(data) != item["image_sha256"]:
            raise ValueError("overlay source checksum mismatch")
        with Image.open(io.BytesIO(data)) as image:
            canvas = image.convert("RGB")

        draw = ImageDraw.Draw(canvas)
        for index, box in enumerate(item["boxes"]):
            class_id, x1, y1, x2, y2 = box
            pixels = [
                math.floor(x1),
                math.floor(y1),
                math.ceil(x2) - 1,
                math.ceil(y2) - 1,
            ]
            draw.rectangle(pixels, outline="red", width=1)
            draw.text(
                (pixels[0], max(0, pixels[1] - 10)),
                f"{index}:{class_id}",
                fill="yellow",
            )
        canvas = canvas.resize(
            (canvas.width * 3, canvas.height * 3),
            resample=Image.Resampling.NEAREST,
        )

    result = io.BytesIO()
    canvas.save(result, format="PNG")
    return result.getvalue()


def make_packet(root: Path, audit_path: Path, output: Path, per_class=5):
    data = audit_path.read_bytes()
    report = json.loads(data)
    manifest, _ = inventory(root)
    if sha256(canonical_json(manifest)) != report["manifest_sha256"]:
        raise ValueError("review source differs from audited source")
    if report["manifest_sha256"] != report["baseline_sha256"]:
        raise ValueError("resolve DQ09 before human review")

    files = {"audit.json": data}
    entries = []
    for item in select_items(report, per_class):
        name = f"overlays/{sha256(item['image'].encode())}.png"
        files[name] = overlay(root, item)
        entries.append(
            {
                "image": item["image"],
                "image_sha256": item["image_sha256"],
                "xml_sha256": item["xml_sha256"],
                "annotation_id": item["annotation_id"],
                "classes": sorted({box[0] for box in item["boxes"]}),
                "overlay": name,
                "requires_quarantine": item["quarantined"],
            }
        )

    selection = {
        "per_class": per_class,
        "report_sha256": sha256(data),
        "files": {name: sha256(value) for name, value in files.items()},
        "items": entries,
    }
    packet_id = sha256(canonical_json(selection))
    review = {
        "packet_id": packet_id,
        "reviewer": "",
        "reviewed_at": "",
        "coordinates": report["coordinates"],
        "coordinate_basis": "",
        "source_endpoint_semantics": "unverified",
        "warning_disposition": "",
        "items": [{**entry, "decision": "pending", "notes": ""} for entry in entries],
    }
    files["selection.json"] = canonical_json(selection)
    files["review.json"] = canonical_json(review)
    write_bundle(root, output, files)
    return {"packet_id": packet_id, "review_items": len(entries)}


def check_review(packet: Path, per_class=5):
    selection = json.loads((packet / "selection.json").read_bytes())
    review = json.loads((packet / "review.json").read_bytes())
    if selection["per_class"] != per_class:
        raise ValueError("review coverage requirement differs")
    if review["packet_id"] != sha256(canonical_json(selection)):
        raise ValueError("review packet identity mismatch")

    for name, expected in selection["files"].items():
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("unsafe review artifact path")
        if sha256((packet / relative).read_bytes()) != expected:
            raise ValueError(f"review artifact changed: {name}")

    report = json.loads((packet / "audit.json").read_bytes())
    if review["coordinates"] != report["coordinates"]:
        raise ValueError("review coordinate convention mismatch")
    for field in ("reviewer", "coordinate_basis", "warning_disposition"):
        if not isinstance(review[field], str) or not review[field].strip():
            raise ValueError(f"review field is incomplete: {field}")
    timestamp = datetime.fromisoformat(review["reviewed_at"])
    if timestamp.tzinfo is None:
        raise ValueError("review timestamp requires timezone")
    if review["source_endpoint_semantics"] != "unverified":
        raise ValueError("source semantics require separately reviewed evidence")

    expected = {item["image"]: item for item in selection["items"]}
    actual = {item["image"]: item for item in review["items"]}
    if len(actual) != len(review["items"]) or set(actual) != set(expected):
        raise ValueError("review membership differs")

    coverage = Counter()
    quarantine = set(report["quarantine"])
    for path, identity in expected.items():
        reviewed = actual[path]
        if any(reviewed.get(key) != value for key, value in identity.items()):
            raise ValueError(f"review item identity differs: {path}")
        if reviewed["decision"] not in ("accept", "quarantine"):
            raise ValueError(f"review decision pending: {path}")
        if not isinstance(reviewed["notes"], str) or not reviewed["notes"].strip():
            raise ValueError(f"review notes missing: {path}")
        if identity["requires_quarantine"] and reviewed["decision"] != "quarantine":
            raise ValueError(f"automated quarantine remains unresolved: {path}")
        if reviewed["decision"] == "quarantine":
            quarantine.add(path)
        coverage.update(identity["classes"])

    if any(coverage[class_id] < per_class for class_id in range(len(CLASSES))):
        raise ValueError("fewer than required reviewed images per class")

    return {
        "packet_id": review["packet_id"],
        "review_sha256": sha256((packet / "review.json").read_bytes()),
        "audit_sha256": selection["report_sha256"],
        "coordinates": report["coordinates"],
        "source_endpoint_semantics": "unverified",
        "reviewed_per_class": {
            CLASSES[index]: coverage[index] for index in range(len(CLASSES))
        },
        "effective_quarantine": sorted(quarantine),
        "dq08_status": report["dq08_status"],
    }
