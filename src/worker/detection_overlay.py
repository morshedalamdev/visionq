"""Render detection overlays exclusively from persisted inference results."""

from __future__ import annotations

import io
import math
from pathlib import Path

from PIL import Image, ImageDraw
from sqlalchemy import MetaData, Table, text
from sqlalchemy.dialects.postgresql import insert

from worker.catalog_store import CatalogConflict, check_blob, store_blob, writer
from worker.inference import ensure_inference_row, inference_tables
from worker.validation import CLASSES, sha256

RENDERER_VERSION = "m3t3-overlay-v1"


def render_overlay(image_bytes, detections, classes=CLASSES):
    """Draw original-coordinate boxes on a copy of decoded image bytes."""
    with Image.open(io.BytesIO(image_bytes)) as source:
        source.load()
        canvas = source.convert("RGB")
    width, height = canvas.size
    draw = ImageDraw.Draw(canvas)
    for detection in detections:
        class_id = detection["class_id"]
        if type(class_id) is not int or class_id not in range(len(classes)):
            raise ValueError("persisted class ID is outside the vocabulary")
        confidence = float(detection["confidence"])
        if not math.isfinite(confidence) or not 0 <= confidence <= 1:
            raise ValueError("persisted confidence must lie in [0, 1]")
        x1 = float(detection["box_xmin"])
        y1 = float(detection["box_ymin"])
        x2 = float(detection["box_xmax"])
        y2 = float(detection["box_ymax"])
        coordinates = (x1, y1, x2, y2)
        if not all(math.isfinite(value) for value in coordinates):
            raise ValueError("persisted coordinates must be finite")
        if x1 < 0 or y1 < 0 or x1 >= x2 or y1 >= y2 or x2 > width or y2 > height:
            raise ValueError("persisted box lies outside the source image")
        rectangle = (
            max(0, math.floor(x1)),
            max(0, math.floor(y1)),
            min(width - 1, math.ceil(x2) - 1),
            min(height - 1, math.ceil(y2) - 1),
        )
        draw.rectangle(rectangle, outline="red", width=2)
        label = f"{classes[class_id]} {confidence:.2f}"
        label_y = max(0, rectangle[1] - 11)
        draw.rectangle(
            (rectangle[0], label_y, rectangle[0] + 100, label_y + 10), fill="red"
        )
        draw.text((rectangle[0] + 1, label_y), label, fill="white")

    result = io.BytesIO()
    canvas.save(result, format="PNG")
    return result.getvalue()


def _artifact_table(connection):
    return Table("catalog_artifacts", MetaData(), autoload_with=connection)


def generate_overlays(engine, artifact_root: Path, run_id, asset_ids=None):
    requested = None if asset_ids is None else {str(value) for value in asset_ids}
    generated = []
    with writer(engine) as connection:
        with connection.begin():
            run = (
                connection.execute(
                    text("""
                    SELECT r.id, m.classes
                    FROM inference_runs AS r
                    JOIN models AS m ON m.id = r.model_id
                    WHERE r.id = CAST(:run AS uuid)
                """),
                    {"run": run_id},
                )
                .mappings()
                .one_or_none()
            )
            if run is None:
                raise CatalogConflict("unknown inference run")
            results = (
                connection.execute(
                    text("""
                    SELECT CAST(ir.asset_id AS text) AS asset_id,
                           ir.image_sha256, ir.detection_count,
                           ca.byte_count AS image_bytes
                    FROM image_results AS ir
                    JOIN catalog_artifacts AS ca
                      ON ca.sha256 = ir.image_sha256
                    WHERE ir.run_id = CAST(:run AS uuid)
                      AND ir.status = 'succeeded'
                    ORDER BY ir.asset_id
                """),
                    {"run": run_id},
                )
                .mappings()
                .all()
            )
            selected = [
                dict(row)
                for row in results
                if requested is None or str(row["asset_id"]) in requested
            ]
            found = {str(row["asset_id"]) for row in results}
            if requested is not None and requested - found:
                raise CatalogConflict("overlay request includes an unprocessed image")

            for row in selected:
                check_blob(artifact_root, row["image_sha256"], row["image_bytes"])
                image_bytes = (
                    Path(artifact_root) / "catalog/objects" / row["image_sha256"]
                ).read_bytes()
                detections = (
                    connection.execute(
                        text("""
                        SELECT ordinal, class_id, confidence,
                               box_xmin, box_ymin, box_xmax, box_ymax
                        FROM detections
                        WHERE run_id = CAST(:run AS uuid)
                          AND asset_id = CAST(:asset AS uuid)
                        ORDER BY ordinal
                    """),
                        {"run": run_id, "asset": row["asset_id"]},
                    )
                    .mappings()
                    .all()
                )
                if len(detections) != row["detection_count"]:
                    raise CatalogConflict("persisted detection count differs")

                overlay = render_overlay(
                    image_bytes,
                    [dict(item) for item in detections],
                    run["classes"],
                )
                overlay_sha = sha256(overlay)
                store_blob(artifact_root, overlay_sha, overlay)
                artifacts = _artifact_table(connection)
                connection.execute(
                    insert(artifacts)
                    .values(sha256=overlay_sha, byte_count=len(overlay))
                    .on_conflict_do_nothing()
                )
                tables = inference_tables(connection)
                overlay_row = {
                    "run_id": run_id,
                    "asset_id": row["asset_id"],
                    "renderer_version": RENDERER_VERSION,
                    "overlay_sha256": overlay_sha,
                    "overlay_bytes": len(overlay),
                    "source_image_sha256": row["image_sha256"],
                    "detection_count": row["detection_count"],
                }
                ensure_inference_row(
                    connection,
                    tables["image_overlays"],
                    overlay_row,
                )
                generated.append(
                    {
                        "asset_id": str(row["asset_id"]),
                        "sha256": overlay_sha,
                        "bytes": len(overlay),
                        "detections": row["detection_count"],
                    }
                )
    return {"run_id": str(run_id), "overlays": generated}
