"""Verified, append-only import of sealed research results; never runs inference."""

import hashlib
import json
from pathlib import Path

from sqlalchemy import text

from worker.catalog_store import CatalogConflict, store_blob, writer
from worker.evaluation import verify_performance


def validate_model(model, evaluation, performance):
    """Bind research lineage to the registered detector, not operational counts."""
    selection = evaluation["selection"]
    checks = [
        (model["checkpoint_sha256"], selection["checkpoint_sha256"]),
        (model["selection_manifest_sha256"], selection["sha256"]),
        (
            model["training_manifest_sha256"],
            evaluation["training_run"]["manifest_sha256"],
        ),
        (model["release_manifest_sha256"], evaluation["dataset"]["manifest_sha256"]),
        (
            model["inference_config"]["settings"],
            evaluation["operating_evaluation"]["settings"],
        ),
        (model["inference_config"]["confidence_threshold"], selection["threshold"]),
        (model["classes"], evaluation["classes"]),
        (performance["selection"], selection),
    ]
    if any(a != b for a, b in checks):
        raise CatalogConflict("evaluation/model provenance mismatch")
    expected = (
        "real-test" if model["evidence_kind"] == "released" else "synthetic-development"
    )
    if (
        evaluation["evidence_class"] != expected
        or performance["evidence_class"] != expected
    ):
        raise CatalogConflict("evaluation evidence kind mismatch")


def register_evidence(
    engine,
    artifact_root,
    model_id,
    evaluation,
    evaluation_sha,
    performance,
    performance_sha,
    export,
    export_sha,
):
    verify_performance(
        performance, performance_sha, evaluation, evaluation_sha, export, export_sha
    )
    paths = [
        (Path(evaluation), "test-evaluation.json", evaluation_sha, "evaluation"),
        (Path(performance), "performance.json", performance_sha, "performance"),
    ]
    documents = [json.loads((root / name).read_bytes()) for root, name, _, _ in paths]
    with writer(engine) as connection:
        with connection.begin():
            model = (
                connection.execute(
                    text("""
                SELECT m.*, d.release_manifest_sha256 FROM models m
                JOIN dataset_versions d ON d.id=m.dataset_version_id
                WHERE m.id=CAST(:id AS uuid)
            """),
                    {"id": model_id},
                )
                .mappings()
                .one()
            )
            validate_model(model, *documents)
            for (root, name, digest, kind), payload in zip(
                paths, documents, strict=True
            ):
                raw = (root / name).read_bytes()
                # Rehash all bytes at ingestion, after independent verification.
                if (
                    hashlib.sha256(raw).hexdigest() != digest
                    or json.loads(raw) != payload
                ):
                    raise CatalogConflict("manifest changed during import")
                for row in payload["artifacts"]:
                    target = root / row["path"]
                    data = target.read_bytes()
                    if (
                        hashlib.sha256(data).hexdigest() != row["sha256"]
                        or len(data) != row["bytes"]
                    ):
                        raise CatalogConflict("artifact changed during import")
                    store_blob(Path(artifact_root), row["sha256"], data)
                store_blob(Path(artifact_root), digest, raw)
                existing = (
                    connection.execute(
                        text(
                            "SELECT manifest_bytes, model_id FROM detector_evidence WHERE sha256=:sha"
                        ),
                        {"sha": digest},
                    )
                    .mappings()
                    .one_or_none()
                )
                if existing:
                    if bytes(existing["manifest_bytes"]) != raw or str(
                        existing["model_id"]
                    ) != str(model_id):
                        raise CatalogConflict("immutable evidence conflict")
                    continue
                connection.execute(
                    text("""
                    INSERT INTO detector_evidence
                    (sha256,kind,dataset_version_id,model_id,evaluation_sha256,payload,manifest_bytes)
                    VALUES (:sha,:kind,:dataset,:model,:evaluation,CAST(:payload AS jsonb),:raw)
                """),
                    dict(
                        sha=digest,
                        kind=kind,
                        dataset=model["dataset_version_id"],
                        model=model["id"],
                        evaluation=evaluation_sha if kind == "performance" else None,
                        payload=json.dumps(payload),
                        raw=raw,
                    ),
                )
    return {
        "model_id": str(model_id),
        "evaluation_sha256": evaluation_sha,
        "performance_sha256": performance_sha,
    }


def scoped_evidence(connection, dataset_version_id, model_id):
    rows = connection.execute(
        text("""
        SELECT sha256,kind,evaluation_sha256,payload FROM detector_evidence
        WHERE dataset_version_id=CAST(:dataset AS uuid) AND model_id=CAST(:model AS uuid)
        ORDER BY kind,sha256
    """),
        {"dataset": str(dataset_version_id), "model": str(model_id)},
    ).mappings()
    items = []
    for row in rows:
        payload = row["payload"]
        # Keep large artifact inventories out of API/MCP evidence responses.
        keys = (
            ("ap_evaluation", "operating_evaluation", "coverage", "error_examples")
            if row["kind"] == "evaluation"
            else ("measurements", "settings", "method", "sampling", "environment")
        )
        items.append(
            {
                "sha256": row["sha256"],
                "kind": row["kind"],
                "evaluation_sha256": row["evaluation_sha256"],
                "evidence_class": payload["evidence_class"],
                "selection": payload["selection"],
                "limitations": payload["limitations"],
                "results": {k: payload[k] for k in keys},
            }
        )
    return {
        "available": bool(items),
        "items": items,
        "scope": "model-level research evidence; not batch or class-filtered prediction metrics",
    }
