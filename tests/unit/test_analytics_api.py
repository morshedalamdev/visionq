from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from analytics.service import SnapshotPersistenceError
from api.main import create_app


def scope():
    return {
        "dataset_version_id": str(uuid4()),
        "batch_id": str(uuid4()),
        "inference_run_id": str(uuid4()),
    }


def test_metrics_endpoint_requires_valid_service_credentials():
    app = create_app(engine=object(), analytics_api_token="secret")
    with TestClient(app) as client:
        assert client.get("/analytics/metrics").status_code == 401
        response = client.get(
            "/analytics/metrics", headers={"Authorization": "Bearer secret"}
        )

    assert response.status_code == 200
    assert response.json()["version"] == "m4t1-v1"


def test_missing_authorization_configuration_fails_closed():
    app = create_app(engine=object())
    with TestClient(app) as client:
        response = client.get("/analytics/metrics")

    assert response.status_code == 503
    assert response.json()["detail"] == "analytics API authorization is not configured"


def test_health_endpoint_is_public_and_non_sensitive():
    app = create_app(engine=object(), analytics_api_token="secret")
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_snapshot_request_validates_uuid_class_and_metric_names():
    app = create_app(engine=object(), analytics_api_token="secret")
    headers = {"Authorization": "Bearer secret"}
    with TestClient(app) as client:
        invalid_class = client.post(
            "/analytics/snapshots",
            headers=headers,
            json={**scope(), "class_id": 6},
        )
        invalid_metric = client.post(
            "/analytics/snapshots",
            headers=headers,
            json={**scope(), "metric_names": ["invented_accuracy"]},
        )
        invalid_id = client.post(
            "/analytics/snapshots",
            headers=headers,
            json={**scope(), "batch_id": "not-a-uuid"},
        )

    assert invalid_class.status_code == 422
    assert invalid_metric.status_code == 422
    assert invalid_id.status_code == 422


def test_stored_snapshot_route_rejects_invalid_id_without_querying_database():
    app = create_app(engine=object(), analytics_api_token="secret")
    with TestClient(app) as client:
        response = client.get(
            "/analytics/snapshots/not-a-uuid",
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "invalid analytics snapshot ID"


def test_persistence_failure_is_an_explicit_service_unavailable(monkeypatch):
    def fail(*args, **kwargs):
        raise SnapshotPersistenceError("test persistence failure")

    monkeypatch.setattr("api.analytics.capture_snapshot", fail)
    app = create_app(engine=object(), analytics_api_token="secret")
    with TestClient(app) as client:
        response = client.post(
            "/analytics/snapshots",
            headers={"Authorization": "Bearer secret"},
            json=scope(),
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "test persistence failure"


def test_context_snapshot_request_accepts_only_complete_authorized_scope_sets(
    monkeypatch,
):
    captured = {}

    def fake_capture(engine, scopes, metrics, corpus, index):
        captured.update(
            scopes=scopes,
            metrics=metrics,
            corpus=corpus,
            index=index,
        )
        return {"id": str(uuid4()), "payload": {"format": "v2"}}

    monkeypatch.setattr(
        "api.analytics.capture_context_snapshot",
        fake_capture,
    )
    app = create_app(engine=object(), analytics_api_token="secret")
    headers = {"Authorization": "Bearer secret"}
    left = {**scope(), "role": "left"}
    right = {**scope(), "role": "right"}
    with TestClient(app) as client:
        valid = client.post(
            "/analytics/context-snapshots",
            headers=headers,
            json={
                "scopes": [left, right],
                "metric_names": ["batch_image_count"],
            },
        )
        missing_right = client.post(
            "/analytics/context-snapshots",
            headers=headers,
            json={"scopes": [left]},
        )
        mismatched_pin = client.post(
            "/analytics/context-snapshots",
            headers=headers,
            json={
                "scopes": [{**scope(), "role": "primary"}],
                "pinned_corpus_version_id": str(uuid4()),
            },
        )

    assert valid.status_code == 201
    assert missing_right.status_code == 422
    assert mismatched_pin.status_code == 422
    assert [role for role, _ in captured["scopes"]] == ["left", "right"]
