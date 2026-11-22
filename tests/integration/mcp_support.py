"""Synthetic evidence builders for MCP PostgreSQL integration."""

from __future__ import annotations

import json
from pathlib import Path

from catalog_support import build_release
from sqlalchemy import text

from analytics.metrics import AnalyticsScope
from worker.catalog import ingest
from worker.inference import (
    register_batch,
    register_model_contract,
    run_inference,
)
from worker.validation import CLASSES, sha256


def build_inference_scope(engine, tmp_path: Path, name: str):
    release_dir = tmp_path / f"{name}-release"
    package, _ = build_release(release_dir, f"synthetic-mcp-{name}", 1)
    root = tmp_path / f"{name}-artifacts"
    ingest(engine, root, package)
    batch = register_batch(engine, root, package.version_id, "test")
    checkpoint = tmp_path / f"{name}.pt"
    checkpoint.write_bytes(f"mcp-{name}".encode())
    model = register_model_contract(
        engine,
        root,
        package.version_id,
        {
            "checkpoint_path": checkpoint,
            "checkpoint_sha256": sha256(checkpoint.read_bytes()),
            "checkpoint_bytes": checkpoint.stat().st_size,
            "training_manifest_sha256": "a" * 64,
            "selection_manifest_sha256": "b" * 64,
            "dataset_manifest_sha256": package.rows["dataset_versions"][0][
                "release_manifest_sha256"
            ],
            "classes": list(CLASSES),
            "evidence_kind": "synthetic",
            "inference_config": {
                "tool_version": "m3t3-v1",
                "checkpoint": "best",
                "predictor": "synthetic",
                "settings": {
                    "imgsz": 320,
                    "conf": 0.001,
                    "iou": 0.7,
                    "max_det": 300,
                },
                "confidence_threshold": 0.07,
                "match_iou": 0.5,
            },
        },
    )
    return {"engine": engine, "root": root, "batch": batch, "model": model}


def run_scope(fixture, device: str, predictor) -> str:
    return run_inference(
        fixture["engine"],
        fixture["root"],
        fixture["batch"]["batch_id"],
        fixture["model"]["id"],
        device,
        predictor=predictor,
    )["run_id"]


def analytics_scope(fixture, run_id: str):
    return AnalyticsScope.from_values(
        fixture["batch"]["dataset_version_id"],
        fixture["batch"]["batch_id"],
        run_id,
    )


def prediction(path, settings, device):
    return [
        {"cls": 1, "conf": 0.9, "box": [0, 0, 4, 4]},
        {"cls": 3, "conf": 0.8, "box": [4, 4, 8, 8]},
    ]


def build_corpus(tmp_path: Path) -> Path:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    documents = {
        "metrics.md": "# Metrics\nred metrics ratio denominator",
        "limits.md": "# Limits\nblue limitations confidence is not accuracy",
    }
    items = []
    for index, (source, content) in enumerate(documents.items()):
        (corpus / source).write_text(content)
        items.append(
            {
                "key": source.removesuffix(".md"),
                "version": "1",
                "title": source.removesuffix(".md").title(),
                "source": source,
                "classification": "development-fixture",
                "metadata": {"ordinal": index},
            }
        )
    manifest = corpus / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "format": "visionq-corpus-manifest-v1",
                "corpus_name": "mcp-fixtures",
                "version": 1,
                "evidence_kind": "development-fixture",
                "documents": items,
                "chunking": {
                    "version": "mcp-v1",
                    "chunk_size": 320,
                    "overlap": 40,
                    "unit": "whitespace-tokens",
                },
            }
        )
    )
    return manifest


def add_quality_issue(engine, dataset_version_id: str, asset_id: str, rule: str):
    with engine.begin() as connection:
        connection.execute(
            text("""
                INSERT INTO quality_issues (
                    id, dataset_version_id, asset_id,
                    rule_id, severity, details
                ) VALUES (
                    gen_random_uuid(), CAST(:dataset AS uuid),
                    CAST(:asset AS uuid), :rule, 'error',
                    CAST(:details AS jsonb)
                )
            """),
            {
                "dataset": dataset_version_id,
                "asset": asset_id,
                "rule": rule,
                "details": '{"captured":"mcp-fixture"}',
            },
        )
