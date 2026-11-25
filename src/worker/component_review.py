"""Conservative allocation, without duplicate or acquisition assertions."""

import io
import json
from collections import Counter
from copy import deepcopy
from datetime import datetime
from html import escape
from pathlib import Path

from PIL import Image, ImageDraw

from worker.inventory import canonical_json, inventory
from worker.preparation import SPLITS, assign_groups, prepare
from worker.review import check_review, overlay
from worker.validation import sha256, write_bundle

POLICY_NAME = "conservative_similarity_component"
ALGORITHM = "dhash-connected-components-v1"


def component_plan(candidate):
    """Contract eligible exact groups along every existing candidate edge."""
    plan = deepcopy(candidate)
    records = {r["group_id"]: r for r in plan["records"]}
    parents = {g: g for g in records}

    def find(g):
        while parents[g] != g:
            g = parents[g]
        return g

    for edge in plan["near_candidates"]:
        a, b = sorted(find(g) for g in edge["groups"])
        parents[b] = a
    members = {}
    for g in sorted(records):
        members.setdefault(find(g), []).append(g)
    groups = []
    for ids in sorted(members.values()):
        groups.append(
            {
                "group_id": sha256(canonical_json(ids)) if len(ids) > 1 else ids[0],
                "members": ids,
                "aliases": [p for g in ids for p in records[g]["aliases"]],
                "categories": sorted(
                    {c for g in ids for c in records[g]["categories"]}
                ),
            }
        )
    official = candidate["official"]
    assignments = assign_groups(groups, official["membership"] if official else None)
    for group in groups:
        for g in group["members"]:
            records[g]["exact_group_id"] = g
            records[g]["group_id"] = group["group_id"]
            records[g]["split"] = assignments[group["group_id"]]
    plan["policy"] = {**plan["policy"], "grouping": POLICY_NAME, "algorithm": ALGORITHM}
    plan["candidate_plan_sha256"] = sha256(canonical_json(candidate))
    plan["component_manifest"] = groups
    plan["component_manifest_sha256"] = sha256(canonical_json(groups))
    for split in SPLITS:
        selected = [r for r in plan["records"] if r["split"] == split]
        plan["stats"][split] = {
            "assets": len(selected),
            "aliases": sum(len(r["aliases"]) for r in selected),
            "source_categories": dict(
                Counter(c for r in selected for c in r["categories"])
            ),
            "boxes_per_class": {
                str(i): sum(b[0] == i for r in selected for b in r["boxes"])
                for i in range(6)
            },
        }
    return plan


def binding(plan):
    if (
        plan["policy"].get("grouping") != POLICY_NAME
        or plan["policy"].get("algorithm") != ALGORITHM
        or sha256(canonical_json(plan["component_manifest"]))
        != plan["component_manifest_sha256"]
    ):
        raise ValueError("component policy or manifest mismatch")
    return {
        "policy": POLICY_NAME,
        "algorithm": ALGORITHM,
        "plan_sha256": sha256(canonical_json(plan)),
        "candidate_plan_sha256": plan["candidate_plan_sha256"],
        "component_manifest_sha256": plan["component_manifest_sha256"],
    }


def make_component_packet(
    root, packet, plan_path, plan_sha, output, official_path=None
):
    receipt = check_review(packet)
    data = plan_path.read_bytes()
    if sha256(data) != plan_sha:
        raise ValueError("plan checksum mismatch")
    plan = json.loads(data)
    if prepare(root, packet, official_path, POLICY_NAME) != plan:
        raise ValueError("plan or reviewed inputs changed")
    report = json.loads((packet / "audit.json").read_bytes())
    records = {r["exact_group_id"]: r for r in plan["records"]}
    groups = [g for g in plan["component_manifest"] if len(g["members"]) > 1]
    files = {"plan.json": data, "t2-receipt.json": canonical_json(receipt)}
    sections, decisions = [], []
    for number, group in enumerate(groups, 1):
        paths = sorted(group["aliases"])
        sheet = Image.new("RGB", (1200, 420 * ((len(paths) + 3) // 4)), "white")
        draw = ImageDraw.Draw(sheet)
        for index, path in enumerate(paths):
            item = report["items"][path]
            preview = overlay(root, item)
            image = Image.open(io.BytesIO(preview))
            image.thumbnail((290, 290), Image.Resampling.NEAREST)
            x, y = (index % 4) * 300, (index // 4) * 420
            sheet.paste(image, (x, y))
            record = next(
                records[g] for g in group["members"] if path in records[g]["aliases"]
            )
            classes = sorted({int(b[0]) for b in item["boxes"]})
            draw.text(
                (x + 3, y + 293),
                f"{Path(path).name}\ncategory: {','.join(record['categories'])}\n"
                + "\n".join(f"{c}: {plan['classes'][c]}" for c in classes),
                fill="black",
            )
            files[f"overlays/{sha256(path.encode())}.png"] = preview
        stream = io.BytesIO()
        sheet.save(stream, format="PNG")
        name = f"sheets/{number:02d}-{group['group_id']}.png"
        files[name] = stream.getvalue()
        links = " ".join(
            f'<a href="overlays/{sha256(p.encode())}.png">{escape(p)}</a>'
            for p in paths
        )
        sections.append(
            f'<section><h2>Component {number}: {len(paths)} images</h2><code>{group["group_id"]}</code><p><a href="{name}">Full-size sheet</a></p><img width="1200" src="{name}"><p>{links}</p></section>'
        )
        decisions.append(
            {"component_id": group["group_id"], "decision": "pending", "notes": ""}
        )
    files["index.html"] = (
        "<!doctype html><meta charset='utf-8'><title>Component review</title><h1>Conservative isolation review</h1><p>No duplicate or acquisition claim. Inspect every image and overlay. Edit component-review.json: accept_isolation only after review; otherwise unresolved. Class IDs: "
        + escape(str(dict(enumerate(plan["classes"]))))
        + "</p>"
        + "".join(sections)
    ).encode()
    files["component-review.json"] = canonical_json(
        {
            **binding(plan),
            "reviewer": "",
            "reviewed_at": "",
            "methodology_approved": False,
            "items": decisions,
        }
    )
    static = {
        p: sha256(b) for p, b in sorted(files.items()) if p != "component-review.json"
    }
    descriptor = {**binding(plan), "static_files": static}
    files["packet.json"] = canonical_json(descriptor)
    current, _ = inventory(root)
    if sha256(canonical_json(current)) != plan["manifest_sha256"]:
        raise ValueError("source changed during packet generation")
    write_bundle(root, output, files)
    return {
        "status": "pending_human_review",
        "components": len(groups),
        "images": sum(len(g["aliases"]) for g in groups),
        "packet_sha256": sha256(files["packet.json"]),
    }


def check_component_review(packet, packet_sha, plan=None):
    """Pinned static evidence plus genuine complete review; no inferred decisions."""
    data = (packet / "packet.json").read_bytes()
    if sha256(data) != packet_sha:
        raise ValueError("component packet checksum mismatch")
    descriptor = json.loads(data)
    for name, digest in descriptor["static_files"].items():
        path = packet / name
        if Path(name).is_absolute() or ".." in Path(name).parts or path.is_symlink():
            raise ValueError("unsafe component packet path")
        if sha256(path.read_bytes()) != digest:
            raise ValueError("component static evidence changed")
    stored_plan = json.loads((packet / "plan.json").read_bytes())
    if plan is not None and plan != stored_plan:
        raise ValueError("stale component review plan")
    expected = binding(stored_plan)
    review_data = (packet / "component-review.json").read_bytes()
    review = json.loads(review_data)
    if any(review.get(k) != v or descriptor.get(k) != v for k, v in expected.items()):
        raise ValueError("component policy binding mismatch")
    if (
        review.get("methodology_approved") is not True
        or not review.get("reviewer", "").strip()
    ):
        raise ValueError("owner methodology confirmation and reviewer required")
    stamp = datetime.fromisoformat(review["reviewed_at"])
    if stamp.tzinfo is None:
        raise ValueError("review time requires timezone")
    ids = {
        g["group_id"]
        for g in stored_plan["component_manifest"]
        if len(g["members"]) > 1
    }
    decisions = review["items"]
    if {i["component_id"] for i in decisions} != ids or len(decisions) != len(ids):
        raise ValueError("component review membership mismatch")
    if any(
        i["decision"] != "accept_isolation" or not i["notes"].strip() for i in decisions
    ):
        raise ValueError("component review incomplete or unresolved")
    return {
        **expected,
        "status": "passed",
        "packet_sha256": packet_sha,
        "review_sha256": sha256(review_data),
        "reviewer": review["reviewer"],
        "reviewed_at": review["reviewed_at"],
        "components": len(ids),
    }
