"""Resumable, database-backed batch inference with immutable result lineage."""

from __future__ import annotations

import json
import math
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

from PIL import Image
from sqlalchemy import MetaData, Table, select, text, update
from sqlalchemy.dialects.postgresql import insert

from worker.catalog_store import (
    CatalogConflict,
    check_blob,
    plain,
    store_blob,
    values_for,
    writer,
)
from worker.evaluation import SELECTION, verify_selection
from worker.inventory import canonical_json
from worker.training import file_sha256
from worker.validation import CLASSES, sha256

INFERENCE_VERSION = "m3t3-v1"
MAX_ATTEMPTS = 3
INFERENCE_TABLES = (
    "models",
    "batches",
    "batch_items",
    "inference_runs",
    "image_results",
    "detections",
    "image_overlays",
)
KEYS = {
    "models": ("id",),
    "batches": ("id",),
    "batch_items": ("batch_id", "asset_id"),
    "inference_runs": ("id",),
    "image_results": ("run_id", "asset_id"),
    "detections": ("run_id", "asset_id", "ordinal"),
    "image_overlays": ("run_id", "asset_id"),
}


def now():
    return datetime.now(UTC)


def inference_tables(connection):
    metadata = MetaData()
    return {
        name: Table(name, metadata, autoload_with=connection)
        for name in INFERENCE_TABLES
    }


def _condition(table, key, expected):
    values = values_for(table, expected)
    return (table.c[column] == values[column] for column in key)


def ensure_inference_row(connection, table, expected, ignored=()):
    key = KEYS[table.name]
    values = values_for(table, expected)
    connection.execute(insert(table).values(**values).on_conflict_do_nothing())
    actual = (
        connection.execute(select(table).where(*_condition(table, key, expected)))
        .mappings()
        .one_or_none()
    )
    if actual is None:
        raise CatalogConflict(f"{table.name}: conflicting unique identity")
    comparable = {name: plain(actual[name]) for name in expected if name not in ignored}
    wanted = {
        name: plain(value) for name, value in expected.items() if name not in ignored
    }
    if comparable != wanted:
        raise CatalogConflict(f"{table.name}: existing row differs")


def identity(kind, value):
    return str(uuid5(NAMESPACE_URL, f"visionq/inference/v1/{kind}/{value}"))


def membership_sha256(dataset_version_id, items):
    payload = {
        "dataset_version_id": str(dataset_version_id),
        "items": [
            {
                "asset_id": str(item["asset_id"]),
                "image_sha256": item["image_sha256"],
            }
            for item in items
        ],
    }
    return sha256(canonical_json(payload))


def selected_model(selection, selection_sha, real_release_approved=False):
    verify_selection(Path(selection), selection_sha)
    saved = json.loads((Path(selection) / SELECTION).read_bytes())
    if saved["evidence_class"] != "synthetic-development" and not real_release_approved:
        raise ValueError(
            "non-synthetic selection needs --real-release-approved after M2 and "
            "M3 release gates pass"
        )
    checkpoint = saved["selected_checkpoint"]
    checkpoint_path = Path(checkpoint["path"])
    if checkpoint_path.is_symlink() or not checkpoint_path.is_file():
        raise ValueError("selected checkpoint is missing")
    if file_sha256(checkpoint_path) != checkpoint["sha256"]:
        raise ValueError("selected checkpoint checksum mismatch")
    return {
        "checkpoint_path": checkpoint_path,
        "checkpoint_sha256": checkpoint["sha256"],
        "checkpoint_bytes": checkpoint_path.stat().st_size,
        "training_manifest_sha256": saved["training_run"]["manifest_sha256"],
        "selection_manifest_sha256": selection_sha,
        "dataset_manifest_sha256": saved["dataset"]["manifest_sha256"],
        "classes": saved["classes"],
        "evidence_kind": (
            "synthetic"
            if saved["evidence_class"] == "synthetic-development"
            else "released"
        ),
        "inference_config": {
            "tool_version": INFERENCE_VERSION,
            "checkpoint": checkpoint["name"],
            "predictor": "ultralytics",
            "preprocessing": "grayscale-rgb",
            "settings": saved["operating_evaluation"]["settings"],
            "confidence_threshold": saved["operating_evaluation"]["selected"][
                "threshold"
            ],
            "match_iou": saved["operating_evaluation"]["match_iou"],
        },
    }


def register_model(
    engine,
    artifact_root: Path,
    dataset_version_id: str,
    selection,
    selection_sha,
    real_release_approved=False,
):
    contract = selected_model(selection, selection_sha, real_release_approved)
    return register_model_contract(
        engine,
        artifact_root,
        dataset_version_id,
        contract,
    )


def register_model_contract(engine, artifact_root: Path, dataset_version_id, contract):
    if contract["classes"] != list(CLASSES):
        raise ValueError("selection class order differs from VisionQ")
    checkpoint_path = Path(contract["checkpoint_path"])
    if checkpoint_path.is_symlink() or not checkpoint_path.is_file():
        raise ValueError("checkpoint is missing")
    if file_sha256(checkpoint_path) != contract["checkpoint_sha256"]:
        raise ValueError("checkpoint checksum mismatch")
    if checkpoint_path.stat().st_size != contract["checkpoint_bytes"]:
        raise ValueError("checkpoint byte count differs from contract")

    with writer(engine) as connection:
        with connection.begin():
            tables = inference_tables(connection)
            reflected = Table(
                "dataset_versions",
                MetaData(),
                autoload_with=connection,
            )
            version = (
                connection.execute(
                    select(reflected).where(reflected.c.id == UUID(dataset_version_id))
                )
                .mappings()
                .one_or_none()
            )
            if version is None:
                raise CatalogConflict("unknown dataset version")
            if (
                version["release_manifest_sha256"]
                != contract["dataset_manifest_sha256"]
            ):
                raise CatalogConflict("selection belongs to another dataset release")
            if version["evidence_kind"] != contract["evidence_kind"]:
                raise CatalogConflict("selection evidence kind differs from dataset")

            checkpoint = checkpoint_path.read_bytes()
            config_sha = sha256(canonical_json(contract["inference_config"]))
            model_id = identity(
                "model",
                canonical_json(
                    {
                        "dataset_version_id": str(dataset_version_id),
                        "checkpoint_sha256": contract["checkpoint_sha256"],
                        "training_manifest_sha256": contract[
                            "training_manifest_sha256"
                        ],
                        "selection_manifest_sha256": contract[
                            "selection_manifest_sha256"
                        ],
                        "config_sha256": config_sha,
                    }
                ).decode(),
            )
            row = {
                "id": model_id,
                "dataset_version_id": dataset_version_id,
                "evidence_kind": contract["evidence_kind"],
                "architecture": "yolo11n",
                "class_map_version": "neu-det-v1",
                "classes": contract["classes"],
                "checkpoint_sha256": contract["checkpoint_sha256"],
                "checkpoint_bytes": len(checkpoint),
                "training_manifest_sha256": contract["training_manifest_sha256"],
                "selection_manifest_sha256": contract["selection_manifest_sha256"],
                "inference_config_sha256": config_sha,
                "inference_config": contract["inference_config"],
            }

            store_blob(artifact_root, contract["checkpoint_sha256"], checkpoint)
            connection.execute(
                insert(Table("catalog_artifacts", MetaData(), autoload_with=connection))
                .values(
                    sha256=contract["checkpoint_sha256"],
                    byte_count=len(checkpoint),
                )
                .on_conflict_do_nothing()
            )
            ensure_inference_row(connection, tables["models"], row)
            created = (
                connection.execute(
                    select(tables["models"]).where(
                        tables["models"].c.id == UUID(model_id)
                    )
                )
                .mappings()
                .one()
            )
    return plain(dict(created))


def _artifact_size(connection, checksum):
    return connection.scalar(
        text("SELECT byte_count FROM catalog_artifacts WHERE sha256 = :checksum"),
        {"checksum": checksum},
    )


def register_batch(
    engine,
    artifact_root: Path,
    dataset_version_id: str,
    split: str,
    asset_ids=None,
    kind="dataset-split",
    real_release_approved=False,
):
    if split not in ("train", "validation", "test"):
        raise ValueError("split must be train, validation or test")
    requested = None if asset_ids is None else [str(value) for value in asset_ids]

    with writer(engine) as connection:
        with connection.begin():
            version = connection.execute(
                text("""
                    SELECT evidence_kind
                    FROM dataset_versions
                    WHERE id = CAST(:version AS uuid)
                """),
                {"version": dataset_version_id},
            ).one_or_none()
            if version is None:
                raise CatalogConflict("unknown dataset version")
            if version[0] != "synthetic" and not real_release_approved:
                raise ValueError(
                    "non-synthetic batch registration needs --real-release-approved"
                )

            rows = (
                connection.execute(
                    text("""
                    SELECT CAST(di.asset_id AS text) AS asset_id,
                           a.raw_sha256 AS image_sha256,
                           a.width, a.height
                    FROM dataset_items AS di
                    JOIN assets AS a ON a.id = di.asset_id
                    WHERE di.dataset_version_id = CAST(:version AS uuid)
                      AND di.split = :split
                    ORDER BY di.asset_id
                """),
                    {"version": dataset_version_id, "split": split},
                )
                .mappings()
                .all()
            )
            items = [dict(row) for row in rows]
            if requested is not None:
                requested_set = set(requested)
                found = {str(item["asset_id"]) for item in items}
                missing = sorted(requested_set - found)
                if missing or len(requested_set) != len(requested):
                    raise CatalogConflict(
                        f"requested assets are not unique members of {split}: {missing}"
                    )
                items = [
                    item for item in items if str(item["asset_id"]) in requested_set
                ]
            if not items:
                raise ValueError("batch has no dataset members")

            digest = membership_sha256(dataset_version_id, items)
            batch_id = identity(
                "batch",
                canonical_json(
                    {
                        "dataset_version_id": str(dataset_version_id),
                        "split": split,
                        "kind": kind,
                        "membership_sha256": digest,
                    }
                ).decode(),
            )
            tables = inference_tables(connection)
            batch = {
                "id": batch_id,
                "dataset_version_id": dataset_version_id,
                "kind": kind,
                "split": split,
                "membership_sha256": digest,
                "member_count": len(items),
            }
            ensure_inference_row(connection, tables["batches"], batch)
            for ordinal, item in enumerate(items):
                size = _artifact_size(connection, item["image_sha256"])
                if size is None:
                    raise CatalogConflict(
                        "batch image is not registered as an artifact"
                    )
                check_blob(artifact_root, item["image_sha256"], size)
                ensure_inference_row(
                    connection,
                    tables["batch_items"],
                    {
                        "batch_id": batch_id,
                        "dataset_version_id": dataset_version_id,
                        "asset_id": item["asset_id"],
                        "ordinal": ordinal,
                        "image_sha256": item["image_sha256"],
                    },
                )
    return {
        "batch_id": batch_id,
        "dataset_version_id": str(dataset_version_id),
        "split": split,
        "membership_sha256": digest,
        "member_count": len(items),
    }


def validate_predictions(raw, width, height, class_count, threshold):
    if not isinstance(raw, list):
        raise ValueError("detector output must be a list")
    if not isinstance(threshold, (int, float)) or not 0 <= threshold <= 1:
        raise ValueError("confidence threshold must lie in [0, 1]")
    kept = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("prediction must be an object")
        class_id = item.get("cls")
        confidence = item.get("conf")
        box = item.get("box")
        if type(class_id) is not int or class_id not in range(class_count):
            raise ValueError("prediction class ID is outside the vocabulary")
        if not isinstance(confidence, (int, float)):
            raise ValueError("prediction confidence must be numeric")
        confidence = float(confidence)
        if not math.isfinite(confidence) or not 0 <= confidence <= 1:
            raise ValueError("prediction confidence must lie in [0, 1]")
        if not isinstance(box, (list, tuple)) or len(box) != 4:
            raise ValueError("prediction box needs four coordinates")
        coordinates = [float(value) for value in box]
        if not all(math.isfinite(value) for value in coordinates):
            raise ValueError("prediction box coordinates must be finite")
        x1, y1, x2, y2 = coordinates
        if x1 < 0 or y1 < 0 or x1 >= x2 or y1 >= y2:
            raise ValueError("prediction box has invalid coordinates")
        if x2 > width or y2 > height:
            raise ValueError("prediction box exceeds image dimensions")
        if confidence >= threshold:
            kept.append(
                {
                    "cls": class_id,
                    "conf": confidence,
                    "box": coordinates,
                }
            )
    return {
        "raw_predictions": raw,
        "raw_prediction_count": len(raw),
        "detections": kept,
        "detection_count": len(kept),
        "prediction_sha256": sha256(canonical_json(raw)),
    }


class UltralyticsPredictor:
    def __init__(self, checkpoint: Path, preprocessing: str = "grayscale-rgb"):
        if preprocessing not in ("grayscale-rgb", "rgb"):
            raise ValueError("unknown detector preprocessing")
        self.preprocessing = preprocessing

        from ultralytics import YOLO

        self._checkpoint_dir = tempfile.TemporaryDirectory(prefix="visionq-inference-")
        staged = Path(self._checkpoint_dir.name) / "checkpoint.pt"
        staged.write_bytes(checkpoint.read_bytes())
        self.model = YOLO(str(staged))

    def __call__(self, image: Path, settings, device):
        with Image.open(image) as source:
            source.load()
            if self.preprocessing == "grayscale-rgb":
                decoded = source.convert("L").convert("RGB")
            else:
                decoded = source.convert("RGB")
        boxes = self.model.predict(
            decoded,
            device=device,
            verbose=False,
            **settings,
        )[0].boxes
        return [
            {
                "cls": int(class_id),
                "conf": float(confidence),
                "box": [float(value) for value in box],
            }
            for box, confidence, class_id in zip(
                boxes.xyxy.tolist(),
                boxes.conf.tolist(),
                boxes.cls.tolist(),
                strict=True,
            )
        ]


def _run_config(model, device):
    if not device or device not in ("cpu", "mps"):
        raise ValueError("device must be cpu or mps")
    return {
        "tool_version": INFERENCE_VERSION,
        "device": device,
        "batch_size": 1,
        "max_attempts": MAX_ATTEMPTS,
        "inference": model["inference_config"],
    }


def run_identity(batch_id, model_id, config):
    return identity(
        "run",
        sha256(
            canonical_json(
                {
                    "batch_id": str(batch_id),
                    "model_id": str(model_id),
                    "config": config,
                }
            )
        ),
    )


def _item_error(connection, tables, run_id, asset_id, message):
    with connection.begin():
        connection.execute(
            update(tables["image_results"])
            .where(tables["image_results"].c.run_id == UUID(str(run_id)))
            .where(tables["image_results"].c.asset_id == UUID(str(asset_id)))
            .values(
                status="failed",
                raw_prediction_count=None,
                detection_count=None,
                prediction_sha256=None,
                latency_ms=None,
                last_error=message,
                finished_at=now(),
            )
        )


def process_item(connection, tables, run, item, artifact_root, predictor, hook):
    asset_id = item["asset_id"]
    with connection.begin():
        current = (
            connection.execute(
                text("""
                SELECT status, attempts, detection_count
                FROM image_results
                WHERE run_id = CAST(:run AS uuid)
                  AND asset_id = CAST(:asset AS uuid)
            """),
                {"run": run["id"], "asset": asset_id},
            )
            .mappings()
            .one()
        )
    if current["status"] == "succeeded":
        check_blob(artifact_root, item["image_sha256"], item["image_bytes"])
        return "succeeded"
    if current["attempts"] >= MAX_ATTEMPTS:
        return "failed"

    with connection.begin():
        connection.execute(
            update(tables["image_results"])
            .where(tables["image_results"].c.run_id == UUID(str(run["id"])))
            .where(tables["image_results"].c.asset_id == UUID(str(asset_id)))
            .where(tables["image_results"].c.status != "succeeded")
            .values(
                status="running",
                attempts=current["attempts"] + 1,
                started_at=now(),
                finished_at=None,
                last_error=None,
            )
        )

    hook("before_prediction", str(asset_id))
    try:
        check_blob(artifact_root, item["image_sha256"], item["image_bytes"])
        image = artifact_root / "catalog/objects" / item["image_sha256"]
        started = time.perf_counter()
        raw = predictor(
            image,
            run["config"]["inference"]["settings"],
            run["config"]["device"],
        )
        elapsed_ms = (time.perf_counter() - started) * 1000
        output = validate_predictions(
            raw,
            item["width"],
            item["height"],
            len(run["classes"]),
            run["config"]["inference"]["confidence_threshold"],
        )
    except Exception as exc:
        message = f"{type(exc).__name__}: image inference failed"
        _item_error(connection, tables, run["id"], asset_id, message)
        hook("after_image_failure", str(asset_id))
        return "failed"

    with connection.begin():
        result = tables["image_results"]
        connection.execute(
            update(result)
            .where(result.c.run_id == UUID(str(run["id"])))
            .where(result.c.asset_id == UUID(str(asset_id)))
            .values(
                status="succeeded",
                raw_prediction_count=output["raw_prediction_count"],
                detection_count=output["detection_count"],
                prediction_sha256=output["prediction_sha256"],
                latency_ms=elapsed_ms,
                last_error=None,
                finished_at=now(),
            )
        )
        detection_table = tables["detections"]
        for ordinal, prediction in enumerate(output["detections"]):
            x1, y1, x2, y2 = prediction["box"]
            connection.execute(
                insert(detection_table).values(
                    run_id=UUID(str(run["id"])),
                    asset_id=UUID(str(asset_id)),
                    status="succeeded",
                    ordinal=ordinal,
                    class_id=prediction["cls"],
                    confidence=prediction["conf"],
                    box_xmin=x1,
                    box_ymin=y1,
                    box_xmax=x2,
                    box_ymax=y2,
                )
            )
        hook("before_item_commit", str(asset_id))
    hook("after_item_commit", str(asset_id))
    return "succeeded"


def _initialize_run(connection, tables, run, items):
    run_row = {
        "id": run["id"],
        "dataset_version_id": run["dataset_version_id"],
        "batch_id": run["batch_id"],
        "model_id": run["model_id"],
        "status": "pending",
        "config_sha256": run["config_sha256"],
        "config": run["config"],
        "expected_items": len(items),
    }
    ensure_inference_row(
        connection,
        tables["inference_runs"],
        run_row,
        ignored=("status", "started_at", "finished_at", "last_error", "created_at"),
    )
    for item in items:
        ensure_inference_row(
            connection,
            tables["image_results"],
            {
                "run_id": run["id"],
                "dataset_version_id": run["dataset_version_id"],
                "batch_id": run["batch_id"],
                "asset_id": item["asset_id"],
                "status": "pending",
                "attempts": 0,
                "image_sha256": item["image_sha256"],
                "raw_prediction_count": None,
                "detection_count": None,
                "prediction_sha256": None,
                "latency_ms": None,
                "last_error": None,
                "started_at": None,
                "finished_at": None,
            },
            ignored=(
                "status",
                "attempts",
                "raw_prediction_count",
                "detection_count",
                "prediction_sha256",
                "latency_ms",
                "last_error",
                "started_at",
                "finished_at",
            ),
        )


def run_inference(
    engine,
    artifact_root: Path,
    batch_id: str,
    model_id: str,
    device: str,
    predictor=None,
    resume_run=None,
    hook=None,
):
    if hook is None:

        def hook(stage, asset_id):
            return None

    with writer(engine) as connection:
        with connection.begin():
            tables = inference_tables(connection)
            batch = (
                connection.execute(
                    text("""
                    SELECT id, dataset_version_id, member_count
                    FROM batches
                    WHERE id = CAST(:batch AS uuid)
                """),
                    {"batch": batch_id},
                )
                .mappings()
                .one_or_none()
            )
            model = (
                connection.execute(
                    text("""
                    SELECT id, dataset_version_id, checkpoint_sha256,
                           checkpoint_bytes, classes, inference_config
                    FROM models
                    WHERE id = CAST(:model AS uuid)
                """),
                    {"model": model_id},
                )
                .mappings()
                .one_or_none()
            )
            if batch is None:
                raise CatalogConflict("unknown batch")
            if model is None:
                raise CatalogConflict("unknown model")
            if batch["dataset_version_id"] != model["dataset_version_id"]:
                raise CatalogConflict("model and batch belong to different datasets")
            config = _run_config(model, device)
            config_sha = sha256(canonical_json(config))
            selected_run = run_identity(batch_id, model_id, config)
            if resume_run is not None and str(resume_run) != selected_run:
                raise CatalogConflict("resume run identity differs from current inputs")
            items = (
                connection.execute(
                    text("""
                    SELECT CAST(bi.asset_id AS text) AS asset_id,
                           bi.image_sha256, bi.ordinal,
                           a.width, a.height, ca.byte_count AS image_bytes
                    FROM batch_items AS bi
                    JOIN assets AS a ON a.id = bi.asset_id
                    JOIN catalog_artifacts AS ca
                      ON ca.sha256 = bi.image_sha256
                    WHERE bi.batch_id = CAST(:batch AS uuid)
                    ORDER BY bi.ordinal
                """),
                    {"batch": batch_id},
                )
                .mappings()
                .all()
            )
            items = [dict(item) for item in items]
            if len(items) != batch["member_count"]:
                raise CatalogConflict("batch membership is incomplete")

            run = {
                "id": selected_run,
                "dataset_version_id": str(batch["dataset_version_id"]),
                "batch_id": str(batch_id),
                "model_id": str(model_id),
                "config_sha256": config_sha,
                "config": config,
                "classes": model["classes"],
            }
            _initialize_run(connection, tables, run, items)

        with connection.begin():
            current = (
                connection.execute(
                    select(tables["inference_runs"]).where(
                        tables["inference_runs"].c.id == UUID(selected_run)
                    )
                )
                .mappings()
                .one()
            )
            if current["status"] == "succeeded":
                report = reconcile_run_connection(
                    connection, artifact_root, selected_run
                )
                if not report["ok"]:
                    raise CatalogConflict(
                        "completed inference no longer reconciles; no repair performed"
                    )
                return report
            connection.execute(
                update(tables["inference_runs"])
                .where(tables["inference_runs"].c.id == UUID(selected_run))
                .values(
                    status="running",
                    started_at=current["started_at"] or now(),
                    finished_at=None,
                    last_error=None,
                )
            )

        try:
            if predictor is None:
                size = model["checkpoint_bytes"]
                check_blob(
                    artifact_root,
                    model["checkpoint_sha256"],
                    size,
                )
                predictor = UltralyticsPredictor(
                    artifact_root / "catalog/objects" / model["checkpoint_sha256"],
                    # Older registered models retain their original RGB input contract.
                    model["inference_config"].get("preprocessing", "rgb"),
                )
            for item in items:
                process_item(
                    connection,
                    tables,
                    run,
                    item,
                    artifact_root,
                    predictor,
                    hook,
                )

            with connection.begin():
                counts = (
                    connection.execute(
                        text("""
                        SELECT
                            count(*) FILTER (WHERE status = 'succeeded') AS succeeded,
                            count(*) FILTER (WHERE status = 'failed') AS failed,
                            count(*) FILTER (WHERE status <> 'succeeded'
                                             AND status <> 'failed') AS other
                        FROM image_results
                        WHERE run_id = CAST(:run AS uuid)
                    """),
                        {"run": selected_run},
                    )
                    .mappings()
                    .one()
                )
                if counts["succeeded"] == len(items):
                    status = "succeeded"
                    last_error = None
                elif counts["succeeded"] > 0:
                    status = "partial"
                    last_error = "one or more images are incomplete"
                else:
                    status = "failed"
                    last_error = "no image completed successfully"
                connection.execute(
                    update(tables["inference_runs"])
                    .where(tables["inference_runs"].c.id == UUID(selected_run))
                    .values(
                        status=status,
                        finished_at=now(),
                        last_error=last_error,
                    )
                )
        except BaseException as exc:
            connection.rollback()
            with connection.begin():
                counts = (
                    connection.execute(
                        text("""
                        SELECT count(*) FILTER (WHERE status = 'succeeded') AS succeeded
                        FROM image_results
                        WHERE run_id = CAST(:run AS uuid)
                    """),
                        {"run": selected_run},
                    )
                    .mappings()
                    .one()
                )
                connection.execute(
                    update(tables["inference_runs"])
                    .where(tables["inference_runs"].c.id == UUID(selected_run))
                    .values(
                        status="partial" if counts["succeeded"] else "failed",
                        finished_at=now(),
                        last_error=f"{type(exc).__name__}: inference interrupted",
                    )
                )
            raise

        hook("before_reconciliation", selected_run)
        with connection.begin():
            report = reconcile_run_connection(connection, artifact_root, selected_run)
        return report


def inference_status(engine, run_id):
    with engine.connect() as connection:
        with connection.begin():
            connection.execute(text("SET TRANSACTION READ ONLY"))
            operation = (
                connection.execute(
                    text("""
                    SELECT id, dataset_version_id, batch_id, model_id, status,
                           config_sha256, expected_items, started_at, finished_at,
                           last_error
                    FROM inference_runs
                    WHERE id = CAST(:run AS uuid)
                """),
                    {"run": run_id},
                )
                .mappings()
                .one_or_none()
            )
            if operation is None:
                raise ValueError("unknown inference run")
            items = connection.execute(
                text("""
                    SELECT status, count(*) AS count
                    FROM image_results
                    WHERE run_id = CAST(:run AS uuid)
                    GROUP BY status
                    ORDER BY status
                """),
                {"run": run_id},
            ).all()
    counts = {status: 0 for status in ("pending", "running", "succeeded", "failed")}
    counts.update({row.status: row.count for row in items})
    return {"operation": plain(dict(operation)), "items": counts}


def _reconcile_membership(connection, run):
    items = (
        connection.execute(
            text("""
            SELECT CAST(asset_id AS text) AS asset_id, image_sha256
            FROM batch_items
            WHERE batch_id = CAST(:batch AS uuid)
              AND dataset_version_id = CAST(:version AS uuid)
            ORDER BY asset_id
        """),
            {
                "batch": run["batch_id"],
                "version": run["dataset_version_id"],
            },
        )
        .mappings()
        .all()
    )
    digest = membership_sha256(run["dataset_version_id"], [dict(row) for row in items])
    saved = connection.scalar(
        text("SELECT membership_sha256 FROM batches WHERE id = CAST(:batch AS uuid)"),
        {"batch": run["batch_id"]},
    )
    return items, digest, saved


def reconcile_run_connection(connection, artifact_root: Path, run_id):
    connection.execute(text("SET TRANSACTION READ ONLY"))
    run = (
        connection.execute(
            text("""
            SELECT id, dataset_version_id, batch_id, model_id, status,
                   config_sha256, config, expected_items
            FROM inference_runs
            WHERE id = CAST(:run AS uuid)
        """),
            {"run": run_id},
        )
        .mappings()
        .one_or_none()
    )
    if run is None:
        raise ValueError("unknown inference run")

    findings = []

    def issue(kind, key, detail=None):
        findings.append({"kind": kind, "key": str(key), "detail": detail})

    if run["config_sha256"] != sha256(canonical_json(run["config"])):
        issue("config_checksum", run_id)
    if run["status"] != "succeeded":
        issue("incomplete_run", run_id, run["status"])

    items, digest, saved_membership = _reconcile_membership(connection, run)
    if digest != saved_membership:
        issue("batch_membership_checksum", run["batch_id"])
    if len(items) != run["expected_items"]:
        issue("batch_member_count", run["batch_id"])

    model = (
        connection.execute(
            text("""
            SELECT checkpoint_sha256, checkpoint_bytes, inference_config
            FROM models
            WHERE id = CAST(:model AS uuid)
              AND dataset_version_id = CAST(:version AS uuid)
        """),
            {
                "model": run["model_id"],
                "version": run["dataset_version_id"],
            },
        )
        .mappings()
        .one_or_none()
    )
    if model is None:
        issue("missing_model", run["model_id"])
    else:
        try:
            check_blob(
                artifact_root,
                model["checkpoint_sha256"],
                model["checkpoint_bytes"],
            )
        except (OSError, ValueError, CatalogConflict):
            issue("corrupt_checkpoint", model["checkpoint_sha256"])

    result_rows = (
        connection.execute(
            text("""
            SELECT CAST(asset_id AS text) AS asset_id, status, image_sha256,
                   raw_prediction_count, detection_count, prediction_sha256,
                   latency_ms, attempts
            FROM image_results
            WHERE run_id = CAST(:run AS uuid)
            ORDER BY asset_id
        """),
            {"run": run_id},
        )
        .mappings()
        .all()
    )
    results = {str(row["asset_id"]): row for row in result_rows}
    expected_assets = {str(row["asset_id"]) for row in items}
    for asset_id in sorted(expected_assets - results.keys()):
        issue("missing_result", asset_id)
    for asset_id in sorted(results.keys() - expected_assets):
        issue("unexpected_result", asset_id)

    for item in items:
        asset_id = str(item["asset_id"])
        result = results.get(asset_id)
        if result is None:
            continue
        size = _artifact_size(connection, item["image_sha256"])
        try:
            if result["image_sha256"] != item["image_sha256"]:
                issue("image_identity", asset_id)
            check_blob(artifact_root, item["image_sha256"], size)
        except (OSError, ValueError, CatalogConflict):
            issue("corrupt_image", item["image_sha256"])

        detection_count = connection.scalar(
            text("""
                SELECT count(*)
                FROM detections
                WHERE run_id = CAST(:run AS uuid)
                  AND asset_id = CAST(:asset AS uuid)
            """),
            {"run": run_id, "asset": asset_id},
        )
        if result["status"] == "succeeded":
            if result["detection_count"] != detection_count:
                issue("detection_count", asset_id)
            if result["raw_prediction_count"] < result["detection_count"]:
                issue("prediction_count", asset_id)
        else:
            issue("incomplete_item", asset_id, result["status"])
            if detection_count:
                issue("unexpected_detections", asset_id)

    overlays = (
        connection.execute(
            text("""
            SELECT io.asset_id, io.overlay_sha256, io.overlay_bytes,
                   io.source_image_sha256, io.detection_count,
                   count(d.ordinal) AS persisted_detections
            FROM image_overlays AS io
            LEFT JOIN detections AS d
              ON d.run_id = io.run_id AND d.asset_id = io.asset_id
            WHERE io.run_id = CAST(:run AS uuid)
            GROUP BY io.asset_id, io.overlay_sha256, io.overlay_bytes,
                     io.source_image_sha256, io.detection_count
        """),
            {"run": run_id},
        )
        .mappings()
        .all()
    )
    for overlay in overlays:
        try:
            check_blob(
                artifact_root,
                overlay["overlay_sha256"],
                overlay["overlay_bytes"],
            )
        except (OSError, ValueError, CatalogConflict):
            issue("corrupt_overlay", overlay["overlay_sha256"])
        if overlay["detection_count"] != overlay["persisted_detections"]:
            issue("overlay_detection_count", overlay["asset_id"])

    findings.sort(key=lambda item: canonical_json(item))
    return {
        "format": "visionq-inference-reconciliation-v1",
        "run_id": str(run_id),
        "batch_id": str(run["batch_id"]),
        "model_id": str(run["model_id"]),
        "ok": not findings,
        "findings": findings,
        "counts": {
            "members": len(items),
            "results": len(result_rows),
            "overlays": len(overlays),
            "detections": sum(
                row["detection_count"] or 0
                for row in result_rows
                if row["status"] == "succeeded"
            ),
        },
    }


def reconcile_run(engine, artifact_root: Path, run_id):
    with engine.connect() as connection:
        connection = connection.execution_options(isolation_level="REPEATABLE READ")
        with connection.begin():
            return reconcile_run_connection(connection, artifact_root, run_id)


def inference_report_text(report):
    lines = [
        f"run={report['run_id']}",
        f"batch={report['batch_id']}",
        f"model={report['model_id']}",
        f"ok={str(report['ok']).lower()}",
    ]
    lines.extend(
        f"{item['kind']} {item['key']} {item['detail'] or ''}".rstrip()
        for item in report["findings"]
    )
    return "\n".join(lines) + "\n"
