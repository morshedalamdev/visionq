"""Create source-bound near-duplicate review packets without making decisions."""

import io
import json
from html import escape
from pathlib import Path

from PIL import Image

from worker.inventory import canonical_json, inventory
from worker.preparation import prepare
from worker.review import check_review
from worker.validation import (
    LIMITS,
    decode_image,
    read_source,
    sha256,
    write_bundle,
)


def make_near_packet(
    root: Path,
    packet: Path,
    plan_path: Path,
    plan_sha: str,
    output: Path,
    official_path: Path | None = None,
):
    receipt = check_review(packet)
    plan_bytes = plan_path.read_bytes()
    if sha256(plan_bytes) != plan_sha:
        raise ValueError("preparation plan checksum mismatch")

    plan = json.loads(plan_bytes)
    if prepare(root, packet, official_path) != plan:
        raise ValueError("plan or reviewed inputs changed; regenerate the plan")

    if receipt["audit_sha256"] != plan["audit_sha256"]:
        raise ValueError("review audit identity differs")
    if receipt["review_sha256"] != plan["review_sha256"]:
        raise ValueError("review identity differs")

    records = {record["group_id"]: record for record in plan["records"]}
    candidates = plan["near_candidates"]
    involved = sorted(
        {group for candidate in candidates for group in candidate["groups"]}
    )

    files = {
        "plan.json": plan_bytes,
        "t2-receipt.json": canonical_json(receipt),
    }
    previews = {}

    for group in involved:
        record = records[group]
        data = read_source(root, record["source"], LIMITS["image_bytes"])
        if sha256(data) != record["asset_id"]:
            raise ValueError("candidate source checksum mismatch")

        decoded = decode_image(data)
        if decoded["pixel_sha256"] != record["pixel_sha256"]:
            raise ValueError("candidate decoded identity mismatch")

        with Image.open(io.BytesIO(data)) as image:
            preview = image.convert("RGB")
            stream = io.BytesIO()
            preview.save(stream, format="PNG")

        name = f"images/{group}.png"
        files[name] = stream.getvalue()
        previews[group] = name
    decisions = []
    sections = []

    for index, candidate in enumerate(candidates, start=1):
        pair_id = sha256(canonical_json(candidate["groups"]))
        decisions.append(
            {
                **candidate,
                "pair_id": pair_id,
                "decision": "pending",
                "reason": "",
            }
        )

        figures = []
        for group in candidate["groups"]:
            record = records[group]
            source = escape(record["source"])
            preview = previews[group]
            figures.append(
                "<figure>"
                f'<a href="{preview}" target="_blank" rel="noopener">'
                f'<img src="{preview}" alt="{source}" loading="lazy">'
                "</a>"
                f"<figcaption>{source}</figcaption>"
                "</figure>"
            )

        sections.append(
            f'<section id="pair-{pair_id}">'
            f"<h2>Pair {index} — distance {candidate['distance']}</h2>"
            f"<code>{pair_id}</code>"
            '<div class="pair">' + "".join(figures) + "</div></section>"
        )

    html = (
        "<!doctype html><html lang='en'><meta charset='utf-8'>"
        "<title>VisionQ near-duplicate review</title>"
        "<style>"
        "body{font-family:system-ui;max-width:1000px;margin:2rem auto}"
        ".pair{display:flex;flex-wrap:wrap}"
        "figure{margin:1rem}"
        "img{width:400px;max-width:90vw;image-rendering:pixelated}"
        "section{border-top:1px solid #aaa;padding:1rem 0}"
        "code{overflow-wrap:anywhere}"
        "</style>"
        "<h1>Near-duplicate candidates — no decisions inferred</h1>"
        "<p>Click an image for its native-size PNG. "
        "Edit near-review.json separately; this page does not save decisions.</p>"
        "<p>Use distinct, related, or unresolved with an observed reason. "
        "A similar texture or dHash alone does not prove shared origin. "
        "Do not bulk-accept pairs or change decisions to preserve a split.</p>"
        + "".join(sections)
        + "</html>"
    )
    files["index.html"] = html.encode("utf-8")
    files["near-review.json"] = canonical_json(
        {
            "schema_version": 1,
            "plan_sha256": plan_sha,
            "reviewer": "",
            "reviewed_at": "",
            "items": decisions,
        }
    )

    # The decision template is intentionally editable. Static evidence is hashed.
    static_files = {
        name: sha256(data)
        for name, data in sorted(files.items())
        if name != "near-review.json"
    }
    files["packet.json"] = canonical_json(
        {
            "schema_version": 1,
            "plan_sha256": plan_sha,
            "candidate_pairs": len(candidates),
            "candidate_images": len(involved),
            "static_files": static_files,
        }
    )

    after, _ = inventory(root)
    if sha256(canonical_json(after)) != plan["manifest_sha256"]:
        raise ValueError("source changed during packet generation")

    write_bundle(root, output, files)
    return {
        "candidate_pairs": len(candidates),
        "candidate_images": len(involved),
        "plan_sha256": plan_sha,
        "status": "pending_human_review",
    }
