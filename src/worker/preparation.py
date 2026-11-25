"""Deterministic preparation plans; reviewed, create-only training exports."""

import io
import json
from collections import Counter, defaultdict
from pathlib import Path

from defusedxml import ElementTree as ET
from PIL import Image

from worker.inventory import canonical_json, inventory
from worker.review import check_review
from worker.validation import (
    CLASSES,
    LIMITS,
    canonical_box,
    decode_image,
    read_source,
    sha256,
    to_yolo,
    validated_boxes,
    write_bundle,
)

SPLITS = ("train", "validation", "test")
POLICY = {
    "version": "m2t3-v1",
    "seed": 42,
    "ratios": [0.70, 0.15, 0.15],
    "near_duplicate": "64-bit dHash, Hamming distance <= 2; review only",
    "acquisition_groups": "unknown; independence beyond detected duplicates unverified",
    "export": "original-size lossless PNG, L converted to three identical RGB bands",
    "resize_owner": "model loader only; record actual scale and padding per image",
    "initial_imgsz": 320,
    "augmentation": "train only; no baseline contrast enhancement or denoising",
}


def letterbox(width, height, target=320):
    """Reference square, non-auto letterbox contract, not an export resize."""
    if min(width, height, target) <= 0:
        raise ValueError("positive geometry required")
    ratio = min(target / width, target / height)
    resized = [round(width * ratio), round(height * ratio)]
    left = (target - resized[0]) // 2
    top = (target - resized[1]) // 2
    return {
        "scale": [resized[0] / width, resized[1] / height],
        "padding": [left, top],
        "source": [width, height],
        "target": target,
    }


def transform_box(box, transform, inverse=False):
    sx, sy = transform["scale"]
    px, py = transform["padding"]
    x1, y1, x2, y2 = box
    if inverse:
        return canonical_box(
            [(x1 - px) / sx, (y1 - py) / sy, (x2 - px) / sx, (y2 - py) / sy],
            *transform["source"],
        )
    canonical_box(box, *transform["source"])
    return [x1 * sx + px, y1 * sy + py, x2 * sx + px, y2 * sy + py]


def exact_groups(items):
    """Transitive union of both byte and decoded-pixel identities."""
    parents = {path: path for path in items}

    def find(path):
        while parents[path] != path:
            path = parents[path]
        return path

    for field in ("image_sha256", "pixel_sha256"):
        seen = {}
        for path, item in sorted(items.items()):
            value = item.get(field)
            if not value:
                raise ValueError(f"missing {field}: {path}")
            if value in seen:
                a, b = sorted((find(path), find(seen[value])))
                parents[b] = a
            seen[value] = path
    groups = defaultdict(list)
    for path in sorted(items):
        groups[find(path)].append(path)
    return sorted(groups.values())


def assign_groups(groups, official=None):
    """Source-category stratification with whole-group weighted allocation."""
    buckets = defaultdict(list)
    for group in groups:
        buckets[tuple(group["categories"])].append(group)
    assignments = {}
    for category, members in sorted(buckets.items()):
        members.sort(key=lambda g: sha256(f"42:{g['group_id']}".encode()))
        if official is not None:
            remaining = []
            for group in members:
                labels = {official[p] for p in group["aliases"]}
                if len(labels) != 1:
                    raise ValueError("official split crosses an exact group")
                if labels == {"test"}:
                    assignments[group["group_id"]] = "test"
                else:
                    remaining.append(group)
            members = remaining
            ratios = (0.70 / 0.85, 0.15 / 0.85)
            names = SPLITS[:2]
        else:
            ratios, names = POLICY["ratios"], SPLITS
        total = sum(len(g["aliases"]) for g in members)
        counts = Counter()
        for group in members:
            chosen = max(
                range(len(names)), key=lambda i: total * ratios[i] - counts[names[i]]
            )
            assignments[group["group_id"]] = names[chosen]
            counts[names[chosen]] += len(group["aliases"])
    return assignments


def dhash(data):
    with Image.open(io.BytesIO(data)) as image:
        pixels = list(image.convert("L").resize((9, 8)).get_flattened_data())
    return sum(
        (pixels[y * 9 + x] > pixels[y * 9 + x + 1]) << (y * 8 + x)
        for y in range(8)
        for x in range(8)
    )


def prepare(
    root: Path, packet: Path, official_path=None, grouping_policy="pair_review"
):
    if grouping_policy != "pair_review":
        from worker.component_review import POLICY_NAME, component_plan

        if grouping_policy != POLICY_NAME:
            raise ValueError("unknown grouping policy")
        return component_plan(prepare(root, packet, official_path))
    return _prepare(root, packet, official_path)


def _prepare(root: Path, packet: Path, official_path=None):
    """Inspect inputs and propose membership. This does not release data."""
    report_bytes = (packet / "audit.json").read_bytes()
    report = json.loads(report_bytes)
    selection = json.loads((packet / "selection.json").read_bytes())
    if sha256(report_bytes) != selection["report_sha256"]:
        raise ValueError("audit checksum mismatch")
    manifest, _ = inventory(root)
    digest = sha256(canonical_json(manifest))
    if digest != report["manifest_sha256"] or digest != report["baseline_sha256"]:
        raise ValueError("source manifest mismatch")
    rows = {row["path"]: row for row in manifest}
    review = json.loads((packet / "review.json").read_bytes())
    # Pending review may add exclusions, never lift automated quarantine.
    excluded = set(report["quarantine"])
    excluded.update(
        i["image"] for i in review["items"] if i["decision"] == "quarantine"
    )
    items = report["items"]
    categories, perceptual = {}, {}
    for path, item in sorted(items.items()):
        if item["image_sha256"] != rows[path]["sha256"]:
            raise ValueError("audit image identity mismatch")
        if item["xml_sha256"] != rows[item["xml"]]["sha256"]:
            raise ValueError("audit XML identity mismatch")
        data = read_source(root, path, LIMITS["image_bytes"])
        decoded = decode_image(data)
        if decoded["pixel_sha256"] != item.get("pixel_sha256"):
            raise ValueError("decoded pixel identity mismatch")
        xml = ET.fromstring(
            read_source(root, item["xml"], LIMITS["xml_bytes"]),
            forbid_dtd=True,
            forbid_entities=True,
            forbid_external=True,
        )
        category = xml.findtext("folder")
        if not category or not category.strip():
            raise ValueError("source category missing; do not infer from object labels")
        categories[path] = category.strip()
        perceptual[path] = dhash(data)
    groups = []
    all_groups = exact_groups(items)
    for aliases in all_groups:
        if excluded.intersection(aliases):
            excluded.update(aliases)
            continue
        signatures = {canonical_json(sorted(items[p]["boxes"])) for p in aliases}
        if len(signatures) != 1:
            raise ValueError("unquarantined conflicting annotations")
        group_id = sha256(
            canonical_json(sorted(items[p]["image_sha256"] for p in aliases))
        )
        groups.append(
            {
                "group_id": group_id,
                "aliases": aliases,
                "categories": sorted({categories[p] for p in aliases}),
            }
        )
    official = None
    official_record = None
    if official_path is not None:
        official_record = json.loads(official_path.read_bytes())
        if not official_record.get("evidence") or not official_record.get(
            "verified_by"
        ):
            raise ValueError("official membership needs provenance verification")
        official = official_record["membership"]
        if set(official) != set(items) or set(official.values()) - {"train", "test"}:
            raise ValueError("official membership must cover every source image")
        for aliases in all_groups:
            if len({official[p] for p in aliases}) != 1:
                raise ValueError("official split crosses an exact group")
    else:
        extras = [
            p
            for p in rows
            if not p.startswith(("IMAGES/", "ANNOTATIONS/"))
            and Path(p).name != ".DS_Store"
        ]
        if extras:
            raise ValueError(
                "review possible supplied partitions before project splitting"
            )
    assignments = assign_groups(groups, official)
    records = []
    for group in groups:
        representative = group["aliases"][0]
        item = items[representative]
        decoded = item["decoded"]
        boxes = validated_boxes(item["boxes"], decoded["width"], decoded["height"])
        records.append(
            {
                **group,
                "split": assignments[group["group_id"]],
                "asset_id": item["image_sha256"],
                "source": representative,
                "pixel_sha256": item["pixel_sha256"],
                "lineage": [
                    {
                        "path": p,
                        "xml": items[p]["xml"],
                        "image_sha256": items[p]["image_sha256"],
                        "xml_sha256": items[p]["xml_sha256"],
                        "annotation_id": items[p]["annotation_id"],
                    }
                    for p in group["aliases"]
                ],
                "boxes": boxes,
                "width": decoded["width"],
                "height": decoded["height"],
            }
        )
    records.sort(key=lambda r: r["group_id"])
    near = []
    for i, left in enumerate(records):
        for right in records[i + 1 :]:
            distance = (
                perceptual[left["source"]] ^ perceptual[right["source"]]
            ).bit_count()
            if distance <= 2:
                near.append(
                    {
                        "groups": [left["group_id"], right["group_id"]],
                        "sources": [left["source"], right["source"]],
                        "distance": distance,
                    }
                )
    stats = {}
    for split in SPLITS:
        members = [r for r in records if r["split"] == split]
        box_counts = Counter(str(b[0]) for r in members for b in r["boxes"])
        stats[split] = {
            "assets": len(members),
            "aliases": sum(len(r["aliases"]) for r in members),
            "source_categories": dict(
                Counter(c for r in members for c in r["categories"])
            ),
            "boxes_per_class": {
                str(i): box_counts[str(i)] for i in range(len(CLASSES))
            },
        }
    return {
        "status": "provisional_not_for_training",
        "policy": POLICY,
        "manifest_sha256": digest,
        "audit_sha256": sha256(report_bytes),
        "review_sha256": sha256((packet / "review.json").read_bytes()),
        "class_map_version": report["class_map_version"],
        "classes": list(CLASSES),
        "coordinates": report["coordinates"],
        "official": official_record,
        "official_split_status": "verified supplied membership"
        if official
        else "unavailable in inspected copy",
        "exact_groups": len(all_groups),
        "excluded": sorted(excluded),
        "near_candidates": near,
        "records": records,
        "stats": stats,
    }


def export(
    root,
    packet,
    plan_path,
    plan_sha,
    output,
    near_review=None,
    official_path=None,
    component_packet=None,
    component_packet_sha=None,
):
    """Fail closed on incomplete human review, drift, or unresolved near duplicates."""
    receipt = check_review(packet)
    data = plan_path.read_bytes()
    if sha256(data) != plan_sha:
        raise ValueError("preparation plan checksum mismatch")
    plan = json.loads(data)
    if (
        prepare(
            root, packet, official_path, plan["policy"].get("grouping", "pair_review")
        )
        != plan
    ):
        raise ValueError("preparation plan or reviewed inputs changed; regenerate plan")
    if any(not all(s["boxes_per_class"].values()) for s in plan["stats"].values()):
        raise ValueError(
            "each split requires all box classes; review grouping feasibility"
        )
    component_receipt = None
    if plan["policy"].get("grouping") == "conservative_similarity_component":
        from worker.component_review import check_component_review

        if component_packet is None or component_packet_sha is None:
            raise ValueError("component review packet and pinned digest required")
        component_receipt = check_component_review(
            component_packet, component_packet_sha, plan
        )
    elif plan["near_candidates"]:
        if near_review is None:
            raise ValueError("near-duplicate review required")
        if near_review.get("plan_sha256") != plan_sha or not near_review.get(
            "reviewer"
        ):
            raise ValueError("near review must bind this plan and identify reviewer")
        decisions = near_review.get("items", [])
        expected = {tuple(c["groups"]) for c in plan["near_candidates"]}
        actual = {tuple(c["groups"]) for c in decisions}
        if actual != expected or len(decisions) != len(expected):
            raise ValueError("near review candidate membership differs")
        for decision in decisions:
            if (
                decision.get("decision") != "distinct"
                or not decision.get("reason", "").strip()
            ):
                raise ValueError(
                    "related or unresolved candidates require grouping review before release"
                )
    files = {}
    for item in plan["records"]:
        raw = read_source(root, item["source"], LIMITS["image_bytes"])
        if sha256(raw) != item["asset_id"]:
            raise ValueError("source changed during export")
        decode_image(raw)
        with Image.open(io.BytesIO(raw)) as image:
            rgb = image.convert("L").convert("RGB")
            stream = io.BytesIO()
            rgb.save(stream, format="PNG")
        split, asset = item["split"], item["asset_id"]
        files[f"images/{split}/{asset}.png"] = stream.getvalue()
        labels = [
            str(box[0])
            + " "
            + " ".join(
                format(v, ".17g")
                for v in to_yolo(box[1:], item["width"], item["height"])
            )
            for box in item["boxes"]
        ]
        files[f"labels/{split}/{asset}.txt"] = ("\n".join(labels) + "\n").encode()
    # An absolute path would destroy reproducibility. M3 supplies the resolved root.
    files["data.yaml"] = (
        "train: images/train\nval: images/validation\ntest: images/test\n"
        + "names:\n"
        + "".join(f"  {i}: {name}\n" for i, name in enumerate(CLASSES))
    ).encode()
    files["release.json"] = canonical_json(
        {
            "schema_version": 1,
            "status": "released",
            "plan": plan,
            "review_receipt": receipt,
            "near_review": near_review,
            **(
                {"component_review_receipt": component_receipt}
                if component_receipt
                else {}
            ),
            "loader_contract": "Set dataset path to resolved export root; imgsz=320; loader owns letterbox; record actual transforms; train-only augmentation",
        }
    )
    manifest = [
        {"path": p, "bytes": len(b), "sha256": sha256(b)}
        for p, b in sorted(files.items())
    ]
    files["manifest.json"] = canonical_json(manifest)
    files["manifest.sha256"] = (sha256(files["manifest.json"]) + "\n").encode()
    current, _ = inventory(root)
    if sha256(canonical_json(current)) != plan["manifest_sha256"]:
        raise ValueError("source changed during export")
    write_bundle(root, output, files)
    return {
        "manifest_sha256": sha256(files["manifest.json"]),
        "assets": len(plan["records"]),
    }


def verify_export(output, expected_sha):
    """Verify exact membership, sizes and bytes against an external digest."""
    data = (output / "manifest.json").read_bytes()
    if sha256(data) != expected_sha:
        raise ValueError("export manifest checksum mismatch")
    rows = json.loads(data)
    names = [r["path"] for r in rows]
    if len(names) != len(set(names)):
        raise ValueError("duplicate manifest paths")
    actual = {
        p.relative_to(output).as_posix() for p in output.rglob("*") if p.is_file()
    }
    if actual != set(names) | {"manifest.json", "manifest.sha256"}:
        raise ValueError("export membership mismatch")
    if (output / "manifest.sha256").read_text().strip() != expected_sha:
        raise ValueError("export checksum sidecar mismatch")
    for row in rows:
        path = Path(row["path"])
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("unsafe export path")
        target = output / path
        if target.is_symlink() or not target.resolve().is_relative_to(output.resolve()):
            raise ValueError("export path escapes root")
        content = target.read_bytes()
        if len(content) != row["bytes"] or sha256(content) != row["sha256"]:
            raise ValueError("export artifact checksum mismatch")
    return {"verified_files": len(rows), "manifest_sha256": expected_sha}
