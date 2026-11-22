"""FastAPI dashboard, secure artifact and upload request integration."""

from __future__ import annotations

import io
from pathlib import Path

from fastapi.testclient import TestClient
from mcp_support import (
    build_inference_scope,
    prediction,
    run_scope,
)
from PIL import Image
from sqlalchemy import text

from api.main import create_app


def png_bytes(size=(18, 12)):
    stream = io.BytesIO()
    Image.new("RGB", size, (20, 80, 120)).save(stream, format="PNG")
    return stream.getvalue()


def dashboard_client(engine, artifact_root: Path):
    app = create_app(
        engine=engine,
        analytics_api_token="dashboard-secret",
        artifact_root=artifact_root,
    )
    return TestClient(app), {"Authorization": "Bearer dashboard-secret"}


def test_dataset_batch_run_and_image_history_are_persisted(postgres_engine, tmp_path):
    fixture = build_inference_scope(postgres_engine, tmp_path, "dashboard-history")
    run_id = run_scope(fixture, "cpu", prediction)
    client, headers = dashboard_client(postgres_engine, fixture["root"])
    try:
        datasets = client.get("/app/datasets", headers=headers)
        batches = client.get(
            "/app/batches",
            headers=headers,
            params={"dataset_version_id": fixture["batch"]["dataset_version_id"]},
        )
        runs = client.get(
            "/app/runs",
            headers=headers,
            params={"batch_id": fixture["batch"]["batch_id"]},
        )
        detail = client.get(f"/app/runs/{run_id}", headers=headers)
        images = client.get(f"/app/runs/{run_id}/images", headers=headers)
    finally:
        client.close()

    assert datasets.status_code == 200
    assert datasets.json()["items"][0]["evidence_kind"] == "synthetic"
    assert batches.status_code == 200
    assert (
        batches.json()["items"][0]["member_count"] == fixture["batch"]["member_count"]
    )
    assert runs.status_code == 200
    assert runs.json()["items"][0]["status"] == "succeeded"
    assert detail.status_code == 200
    assert detail.json()["model_sha256"] == fixture["model"]["checkpoint_sha256"]
    assert images.status_code == 200
    first = images.json()["items"][0]
    assert first["status"] == "succeeded"
    assert first["detection_count"] == 2
    assert first["detections"][0]["class_name"] == "inclusion"
    assert first["detections"][0]["box_xmin"] == 0


def test_secure_artifact_delivery_requires_auth_and_known_checksum(
    postgres_engine, tmp_path
):
    fixture = build_inference_scope(postgres_engine, tmp_path, "artifact")
    run_id = run_scope(fixture, "cpu", prediction)
    client, headers = dashboard_client(postgres_engine, fixture["root"])
    try:
        images = client.get(f"/app/runs/{run_id}/images", headers=headers).json()[
            "items"
        ]
        checksum = images[0]["image_sha256"]
        denied = client.get(f"/app/artifacts/{checksum}")
        delivered = client.get(f"/app/artifacts/{checksum}", headers=headers)
        unknown = client.get(f"/app/artifacts/{'f' * 64}", headers=headers)
        arbitrary = client.get("/app/artifacts/../../secret", headers=headers)
    finally:
        client.close()

    assert denied.status_code == 401
    assert delivered.status_code == 200
    assert delivered.content.startswith(b"\x89PNG")
    assert unknown.status_code == 404
    assert arbitrary.status_code == 404


def test_upload_request_validates_bytes_and_persists_after_restart(
    postgres_engine, tmp_path
):
    artifact_root = tmp_path / "artifacts"
    client, headers = dashboard_client(postgres_engine, artifact_root)
    content = png_bytes((19, 13))
    try:
        invalid = client.post(
            "/app/uploads",
            headers=headers,
            files={"file": ("unsafe.svg", b"<svg/>", "image/svg+xml")},
        )
        corrupt = client.post(
            "/app/uploads",
            headers=headers,
            files={"file": ("broken.png", b"not-an-image", "image/png")},
        )
        created = client.post(
            "/app/uploads",
            headers=headers,
            files={"file": ("sample.png", content, "image/png")},
        )
        upload_id = created.json()["id"]
        staged = client.get(f"/app/uploads/{upload_id}/image", headers=headers)
    finally:
        client.close()

    assert invalid.status_code == 422
    assert corrupt.status_code == 422
    assert created.status_code == 201
    assert created.json()["inference_state"] == "not_started"
    assert created.json()["status"] == "ready"
    assert staged.status_code == 200
    assert staged.content == content

    reopened_client, reopened_headers = dashboard_client(postgres_engine, artifact_root)
    try:
        history = reopened_client.get("/app/uploads", headers=reopened_headers)
        detail = reopened_client.get(
            f"/app/uploads/{upload_id}", headers=reopened_headers
        )
    finally:
        reopened_client.close()
    assert any(item["id"] == upload_id for item in history.json()["items"])
    assert detail.status_code == 200

    assert len(list((artifact_root / "uploads" / "objects").iterdir())) == 1
    with postgres_engine.connect() as connection:
        upload_count = connection.scalar(
            text("""
                SELECT count(*)
                FROM image_upload_requests
                WHERE content_sha256 = :checksum
            """),
            {"checksum": created.json()["content_sha256"]},
        )
    assert upload_count == 1


def test_upload_idempotency_preserves_one_request_and_one_blob(
    postgres_engine, tmp_path
):
    root = tmp_path / "artifacts"
    client, headers = dashboard_client(postgres_engine, root)
    content = png_bytes((21, 14))
    try:
        first = client.post(
            "/app/uploads",
            headers=headers,
            files={"file": ("same.png", content, "image/png")},
        )
        second = client.post(
            "/app/uploads",
            headers=headers,
            files={"file": ("same.png", content, "image/png")},
        )
    finally:
        client.close()
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    with postgres_engine.connect() as connection:
        count = connection.scalar(
            text("""
                SELECT count(*)
                FROM image_upload_requests
                WHERE content_sha256 = :checksum
            """),
            {"checksum": first.json()["content_sha256"]},
        )
    assert count == 1


def test_context_snapshot_comparison_uses_canonical_saved_evidence(
    postgres_engine, tmp_path
):
    fixture = build_inference_scope(postgres_engine, tmp_path, "comparison")
    left = run_scope(fixture, "cpu", lambda *args: [])
    right = run_scope(fixture, "mps", prediction)
    client, headers = dashboard_client(postgres_engine, fixture["root"])
    try:
        snapshot = client.post(
            "/analytics/context-snapshots",
            headers=headers,
            json={
                "scopes": [
                    {
                        "role": "left",
                        "dataset_version_id": fixture["batch"]["dataset_version_id"],
                        "batch_id": fixture["batch"]["batch_id"],
                        "inference_run_id": left,
                    },
                    {
                        "role": "right",
                        "dataset_version_id": fixture["batch"]["dataset_version_id"],
                        "batch_id": fixture["batch"]["batch_id"],
                        "inference_run_id": right,
                    },
                ],
                "metric_names": [
                    "predicted_box_count",
                    "prediction_image_ratio",
                ],
            },
        )
        comparison = client.post(
            f"/analytics/context-snapshots/{snapshot.json()['id']}/compare",
            headers=headers,
            json=["predicted_box_count", "prediction_image_ratio"],
        )
    finally:
        client.close()

    assert snapshot.status_code == 201
    assert comparison.status_code == 200
    boxes = next(
        item
        for item in comparison.json()["metrics"]
        if item["metric_name"] == "predicted_box_count"
    )
    assert boxes["relative_delta"] is None
    assert boxes["relative_delta_reason"] == "zero_left_value"


def test_api_rejects_invalid_pagination_and_fixture_is_labeled(
    postgres_engine, tmp_path
):
    client, headers = dashboard_client(postgres_engine, tmp_path / "artifacts")
    try:
        invalid = client.get("/app/datasets", headers=headers, params={"limit": 101})
        fixture = client.get("/app/agent-fixture", headers=headers)
        denied = client.get("/app/datasets")
    finally:
        client.close()

    assert invalid.status_code == 422
    assert fixture.status_code == 200
    assert fixture.json()["evidence_kind"] == "development-fixture"
    assert fixture.json()["verification_status"] == "fixture-not-verified"
    assert denied.status_code == 401
