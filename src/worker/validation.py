"""Validate preserved dataset inputs and retain annotation lineage."""

import hashlib
import io
import math
import tempfile
import warnings
from collections import Counter, defaultdict
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from xml.etree.ElementTree import ParseError

from defusedxml import ElementTree as SafeET
from defusedxml.common import DefusedXmlException
from PIL import Image, ImageChops, ImageStat

from worker.inventory import IMAGE_SUFFIXES, canonical_json, inventory

RULESET = "m2t2-v1"
CLASS_MAP_VERSION = "neu-det-v1"
CLASSES = (
    "crazing",
    "inclusion",
    "patches",
    "pitted_surface",
    "rolled_in_scale",
    "scratches",
)
CLASS_IDS = {name: index for index, name in enumerate(CLASSES)}
CLASS_IDS["rolled-in_scale"] = CLASS_IDS["rolled_in_scale"]

COORDINATES = ("one-based-inclusive", "zero-based-half-open")
LIMITS = {
    "image_bytes": 20_000_000,
    "xml_bytes": 2_000_000,
    "pixels": 1_000_000,
    "expected_size": [200, 200],
}
REFERENCE = {
    "class_images": {
        "0": 300,
        "1": 382,
        "2": 342,
        "3": 301,
        "4": 300,
        "5": 300,
    },
    "brightness_mean": None,
    "brightness_tolerance": 20,
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def finding(rule, severity, observed, expected):
    action = "review"
    if severity == "error":
        action = "block" if rule in ("DQ08", "DQ09") else "quarantine"
    return {
        "ruleset": RULESET,
        "rule": rule,
        "severity": severity,
        "observed": str(observed),
        "expected": str(expected),
        "action": action,
    }


def read_source(root: Path, relative: str, limit: int) -> bytes:
    relative_path = Path(relative)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise ValueError("expected a source-relative path")
    path = root / relative_path
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("source path escapes its root or is a symlink")
    with path.open("rb") as stream:
        return stream.read(limit + 1)


def write_bundle(root: Path, output: Path, files: dict[str, bytes]) -> None:
    root = root.resolve()
    output = output.resolve()
    if output.is_relative_to(root):
        raise ValueError("output must be outside the source root")
    if output.exists():
        raise FileExistsError(output)

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as temporary:
        staged = Path(temporary) / "bundle"
        staged.mkdir()
        for name, data in files.items():
            relative = Path(name)
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("unsafe artifact member")
            target = staged / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        output.mkdir()
        try:
            staged.replace(output)
        except OSError:
            output.rmdir()
            raise


def canonical_box(values, width, height):
    if len(values) != 4:
        raise ValueError("a box requires four coordinates")
    if any(isinstance(value, bool) for value in values):
        raise ValueError("boolean coordinates are invalid")
    x1, y1, x2, y2 = map(float, values)
    if not all(math.isfinite(value) for value in (x1, y1, x2, y2)):
        raise ValueError("coordinates must be finite")
    if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
        raise ValueError("box must be ordered, nonempty and inside the image")
    return [x1, y1, x2, y2]


def source_box(values, width, height, coordinates):
    if coordinates not in COORDINATES:
        raise ValueError("unknown coordinate convention")
    box = list(map(float, values))
    if len(box) != 4 or not all(
        math.isfinite(value) and value.is_integer() for value in box
    ):
        raise ValueError("source coordinates must be finite integers")
    if coordinates == "one-based-inclusive":
        box[0] -= 1
        box[1] -= 1
    return canonical_box(box, width, height)


def to_source(box, coordinates):
    result = list(box)
    if coordinates == "one-based-inclusive":
        result[0] += 1
        result[1] += 1
    elif coordinates != "zero-based-half-open":
        raise ValueError("unknown coordinate convention")
    return result


def to_yolo(box, width, height):
    x1, y1, x2, y2 = canonical_box(box, width, height)
    return [
        (x1 + x2) / (2 * width),
        (y1 + y2) / (2 * height),
        (x2 - x1) / width,
        (y2 - y1) / height,
    ]


def from_yolo(values, width, height):
    cx, cy, box_width, box_height = map(float, values)
    return canonical_box(
        [
            (cx - box_width / 2) * width,
            (cy - box_height / 2) * height,
            (cx + box_width / 2) * width,
            (cy + box_height / 2) * height,
        ],
        width,
        height,
    )


def validated_boxes(boxes, width, height):
    if not isinstance(boxes, list) or not boxes:
        raise ValueError("supervised annotations require at least one box")
    result = []
    for box in boxes:
        if not isinstance(box, list) or len(box) != 5:
            raise ValueError("expected [class_id, xmin, ymin, xmax, ymax]")
        class_id = box[0]
        if type(class_id) is not int or class_id not in range(len(CLASSES)):
            raise ValueError("unknown canonical class ID")
        result.append([class_id, *canonical_box(box[1:], width, height)])
    return result


def decode_image(data):
    if len(data) > LIMITS["image_bytes"]:
        raise ValueError("image exceeds byte limit")

    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(io.BytesIO(data)) as image:
            width, height = image.size
            if width <= 0 or height <= 0 or width * height > LIMITS["pixels"]:
                raise ValueError("image exceeds geometry limits")
            if (
                getattr(image, "is_animated", False)
                or getattr(image, "n_frames", 1) != 1
            ):
                raise ValueError("multiple image frames are unsupported")
            image.verify()

        with Image.open(io.BytesIO(data)) as image:
            image.load()
            rgb = image.convert("RGB")
            red, green, blue = rgb.split()
            equal_channels = (
                ImageChops.difference(red, green).getbbox() is None
                and ImageChops.difference(red, blue).getbbox() is None
            )
            return {
                "width": image.width,
                "height": image.height,
                "mode": image.mode,
                "bands": len(image.getbands()),
                "orientation": image.getexif().get(274, 1),
                "equal_rgb_channels": equal_channels,
                "brightness": ImageStat.Stat(image.convert("L")).mean[0],
                "pixel_sha256": sha256(
                    f"{image.width}x{image.height}:RGB:".encode() + rgb.tobytes()
                ),
            }


def one_text(node, path):
    matches = node.findall(path)
    if len(matches) != 1 or matches[0].text is None:
        raise ValueError(f"missing or repeated XML field: {path}")
    return matches[0].text


def inspect_pair(image_data, xml_data, image_name, coordinates):
    item = {
        "image": image_name,
        "coordinates": coordinates,
        "decoded": None,
        "raw_objects": [],
        "boxes": [],
        "issues": [],
        "revision_history": [],
    }
    issues = item["issues"]

    try:
        decoded = decode_image(image_data)
        item["decoded"] = decoded
    except (
        OSError,
        ValueError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        issues.append(finding("DQ01", "error", exc, "bounded complete decoding"))
        return item

    width, height = decoded["width"], decoded["height"]
    if decoded["mode"] not in ("L", "RGB") or decoded["orientation"] != 1:
        issues.append(
            finding("DQ02", "error", decoded, "L/RGB image in original orientation")
        )
    if [width, height] != LIMITS["expected_size"] or decoded["mode"] != "L":
        issues.append(
            finding(
                "DQ02",
                "warning",
                decoded,
                "review source geometry and grayscale representation",
            )
        )

    try:
        if xml_data is None:
            raise ValueError("missing or ambiguous annotation")
        if len(xml_data) > LIMITS["xml_bytes"]:
            raise ValueError("XML exceeds byte limit")
        tree = SafeET.fromstring(
            xml_data,
            forbid_dtd=True,
            forbid_entities=True,
            forbid_external=True,
        )
        if tree.tag != "annotation":
            raise ValueError("expected annotation root")
        declared = one_text(tree, "filename")
        actual = Path(image_name).name
        if declared not in (actual, Path(actual).stem):
            raise ValueError("XML filename disagrees with paired image")
        if declared != actual:
            issues.append(
                finding(
                    "DQ03",
                    "warning",
                    declared,
                    "extensionless declaration accepted through exact stem pairing",
                )
            )
        objects = tree.findall("object")
        if not objects:
            raise ValueError("empty supervised annotation")
    except (ParseError, DefusedXmlException, ValueError) as exc:
        issues.append(finding("DQ03", "error", exc, "safe paired annotation"))
        return item

    try:
        dimensions = [
            int(one_text(tree, f"size/{field}"))
            for field in ("width", "height", "depth")
        ]
        if dimensions[:2] != [width, height] or dimensions[2] <= 0:
            raise ValueError(f"declared size {dimensions}, decoded {decoded}")
        if dimensions[2] != decoded["bands"]:
            issues.append(
                finding(
                    "DQ06",
                    "warning",
                    dimensions,
                    "review declared depth versus decoded bands",
                )
            )
    except ValueError as exc:
        issues.append(finding("DQ06", "error", exc, "matching width and height"))

    for index, obj in enumerate(objects):
        try:
            name = one_text(obj, "name")
            values = [
                one_text(obj, f"bndbox/{field}")
                for field in ("xmin", "ymin", "xmax", "ymax")
            ]
        except ValueError as exc:
            issues.append(finding("DQ03", "error", exc, "complete object fields"))
            continue

        item["raw_objects"].append(
            {
                "index": index,
                "name": name,
                "coordinates": values,
            }
        )
        class_id = CLASS_IDS.get(name)
        if class_id is None:
            issues.append(finding("DQ04", "error", name, CLASS_MAP_VERSION))
        try:
            box = source_box(values, width, height, coordinates)
        except ValueError as exc:
            issues.append(finding("DQ05", "error", exc, "valid canonical box"))
            continue
        if class_id is not None:
            item["boxes"].append([class_id, *box])

    return item


def make_revision(item, boxes, author, reason):
    if not author.strip() or not reason.strip():
        raise ValueError("correction author and reason are required")
    blocked = {"DQ01", "DQ02", "DQ03", "DQ06", "DQ09"}
    if any(
        issue["severity"] == "error" and issue["rule"] in blocked
        for issue in item["issues"]
    ):
        raise ValueError("structural input errors require review before correction")
    decoded = item["decoded"]
    boxes = validated_boxes(boxes, decoded["width"], decoded["height"])
    return {
        "schema_version": 1,
        "image": item["image"],
        "image_sha256": item["image_sha256"],
        "xml_sha256": item["xml_sha256"],
        "coordinates": item["coordinates"],
        "class_map_version": CLASS_MAP_VERSION,
        "parent": item["annotation_id"],
        "author": author.strip(),
        "reason": reason.strip(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "boxes": boxes,
    }


def apply_revision(item, revision):
    for key in ("image", "image_sha256", "xml_sha256", "coordinates"):
        if revision[key] != item[key]:
            raise ValueError(f"revision source mismatch: {key}")
    if revision["parent"] != item["annotation_id"]:
        raise ValueError("revision parent mismatch")
    if revision["class_map_version"] != CLASS_MAP_VERSION:
        raise ValueError("revision class map mismatch")
    if revision["schema_version"] != 1:
        raise ValueError("unsupported revision schema")
    timestamp = datetime.fromisoformat(revision["created_at"])
    if timestamp.tzinfo is None:
        raise ValueError("revision timestamp requires timezone")
    validated = make_revision(
        item, revision["boxes"], revision["author"], revision["reason"]
    )
    item.setdefault("source_issues", list(item["issues"]))
    item["issues"] = [
        issue for issue in item["issues"] if issue["rule"] not in ("DQ04", "DQ05")
    ]
    item["boxes"] = validated["boxes"]
    item["revision_history"].append(revision)
    item["annotation_id"] = sha256(canonical_json(revision))


def split_findings(assignments):
    groups = defaultdict(set)
    for assignment in assignments:
        split = assignment["split"]
        if split not in ("train", "validation", "test"):
            raise ValueError("unknown split")
        if not assignment["group"]:
            raise ValueError("missing group identity")
        groups[assignment["group"]].add(split)
    return [
        finding("DQ08", "error", sorted(splits), f"group {group} in one split")
        for group, splits in sorted(groups.items())
        if len(splits) > 1
    ]


def duplicate_findings(items):
    results = []
    seen_members = set()
    for field in ("image_sha256", "pixel_sha256"):
        groups = defaultdict(list)
        for item in items.values():
            value = item.get(field)
            if value:
                groups[value].append(item)

        for checksum, members in sorted(groups.items()):
            if len(members) < 2:
                continue
            paths = tuple(sorted(item["image"] for item in members))
            if paths in seen_members:
                continue
            seen_members.add(paths)
            signatures = {canonical_json(sorted(item["boxes"])) for item in members}
            conflict = len(signatures) > 1
            severity = "error" if conflict else "warning"
            for item in members:
                item["issues"].append(
                    finding(
                        "DQ07",
                        severity,
                        paths,
                        "review identical content and retain source aliases",
                    )
                )
            results.append(
                {
                    "identity": field,
                    "sha256": checksum,
                    "members": list(paths),
                    "conflicting_annotations": conflict,
                }
            )
    return results


def distribution(items, reference):
    counts = Counter()
    brightness = []
    for item in items.values():
        counts.update({str(box[0]) for box in item["boxes"]})
        if item["decoded"] is not None:
            brightness.append(item["decoded"]["brightness"])
    stats = {
        "class_images": {
            str(index): counts[str(index)] for index in range(len(CLASSES))
        },
        "brightness_mean": (sum(brightness) / len(brightness) if brightness else None),
    }
    issues = []
    for label, expected in reference["class_images"].items():
        actual = stats["class_images"].get(label, 0)
        if actual != expected:
            issues.append(
                finding(
                    "DQ10",
                    "warning",
                    {"class_id": label, "images": actual},
                    {"reference_images": expected},
                )
            )
    expected_mean = reference.get("brightness_mean")
    actual_mean = stats["brightness_mean"]
    if expected_mean is not None and actual_mean is not None:
        tolerance = reference.get("brightness_tolerance", 20)
        if abs(actual_mean - expected_mean) > tolerance:
            issues.append(
                finding(
                    "DQ10",
                    "warning",
                    actual_mean,
                    f"reference mean {expected_mean}, tolerance {tolerance}",
                )
            )
    return stats, issues


def audit(
    root: Path,
    baseline: Path,
    baseline_sha: str,
    coordinates: str,
    revisions=None,
    reference=None,
):
    if coordinates not in COORDINATES:
        raise ValueError("choose an explicit coordinate convention")
    baseline_bytes = baseline.read_bytes()
    if sha256(baseline_bytes) != baseline_sha:
        raise ValueError("baseline manifest checksum mismatch")

    root = root.resolve(strict=True)
    manifest, source = inventory(root)
    current_sha = sha256(canonical_json(manifest))
    issues = []
    if current_sha != baseline_sha:
        issues.append(finding("DQ09", "error", current_sha, baseline_sha))

    paired = {pair["image"]: pair["xml"] for pair in source["pairs"]}
    rows = {row["path"]: row for row in manifest}
    items = {}

    for row in manifest:
        path = Path(row["path"])
        if path.parts[0] != "IMAGES" or path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        image_path = row["path"]
        xml_path = paired.get(image_path)
        image_data = read_source(root, image_path, LIMITS["image_bytes"])
        xml_data = (
            read_source(root, xml_path, LIMITS["xml_bytes"])
            if xml_path is not None
            else None
        )
        item = inspect_pair(image_data, xml_data, image_path, coordinates)
        item["xml"] = xml_path
        item["image_sha256"] = row["sha256"]
        item["xml_sha256"] = rows[xml_path]["sha256"] if xml_path else None
        item["annotation_id"] = sha256(
            canonical_json(
                {
                    "image_sha256": item["image_sha256"],
                    "xml_sha256": item["xml_sha256"],
                    "coordinates": coordinates,
                    "class_map_version": CLASS_MAP_VERSION,
                }
            )
        )
        if item["decoded"] is not None:
            item["pixel_sha256"] = item["decoded"]["pixel_sha256"]
        items[image_path] = item

    for path in source["xml_without_images"]:
        issues.append(finding("DQ03", "error", path, "paired image"))

    for revision in revisions or []:
        if revision["image"] not in items:
            raise ValueError("revision references an unknown image")
        apply_revision(items[revision["image"]], revision)

    duplicates = duplicate_findings(items)
    reference = REFERENCE if reference is None else reference
    stats, distribution_issues = distribution(items, reference)
    issues.extend(distribution_issues)

    source_changed = any(
        issue["rule"] == "DQ09" and issue["severity"] == "error" for issue in issues
    )
    for item in items.values():
        item["quarantined"] = source_changed or any(
            issue["severity"] == "error" for issue in item["issues"]
        )

    after, _ = inventory(root)
    if after != manifest:
        raise ValueError("source changed during validation")

    return {
        "schema_version": 1,
        "ruleset": RULESET,
        "class_map_version": CLASS_MAP_VERSION,
        "classes": list(CLASSES),
        "source_aliases": {"rolled-in_scale": "rolled_in_scale"},
        "coordinates": coordinates,
        "coordinate_status": "candidate_until_human_review",
        "manifest_sha256": current_sha,
        "baseline_sha256": baseline_sha,
        "limits": dict(LIMITS),
        "libraries": {
            "pillow": version("Pillow"),
            "defusedxml": version("defusedxml"),
        },
        "items": items,
        "issues": issues,
        "duplicates": duplicates,
        "stats": stats,
        "reference": reference,
        "dq08_status": "pending_real_memberships_in_M2.T3",
        "quarantine": sorted(
            path for path, item in items.items() if item["quarantined"]
        ),
    }
