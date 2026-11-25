from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from api.main import create_app
from retrieval.embeddings import DeterministicEmbeddingBackend


def request_body():
    return {
        "corpus_version_id": str(uuid4()),
        "index_id": str(uuid4()),
        "query": "metric definitions",
        "top_k": 4,
    }


def test_retrieval_requires_authorization_before_backend():
    app = create_app(
        engine=object(),
        analytics_api_token="secret",
        retrieval_backend=None,
    )
    with TestClient(app) as client:
        unauthorized = client.post("/retrieval/search", json=request_body())
        unconfigured = client.post(
            "/retrieval/search",
            headers={"Authorization": "Bearer secret"},
            json=request_body(),
        )

    assert unauthorized.status_code == 401
    assert unconfigured.status_code == 503
    assert unconfigured.json()["detail"] == (
        "retrieval embedding backend is not configured"
    )


def test_retrieval_request_validation_limits_top_k_and_query(monkeypatch):
    app = create_app(
        engine=object(),
        analytics_api_token="secret",
        retrieval_backend=DeterministicEmbeddingBackend(),
    )
    monkeypatch.setattr(
        "api.retrieval.search",
        lambda *args, **kwargs: {"results": []},
    )
    with TestClient(app) as client:
        blank = client.post(
            "/retrieval/search",
            headers={"Authorization": "Bearer secret"},
            json={**request_body(), "query": " "},
        )
        too_many = client.post(
            "/retrieval/search",
            headers={"Authorization": "Bearer secret"},
            json={**request_body(), "top_k": 21},
        )
        valid = client.post(
            "/retrieval/search",
            headers={"Authorization": "Bearer secret"},
            json=request_body(),
        )

    assert blank.status_code == 422
    assert too_many.status_code == 422
    assert valid.status_code == 200


def test_configured_live_profile_surfaces_an_outage(monkeypatch):
    import httpx

    def unavailable(*args, **kwargs):
        raise httpx.ConnectError("private endpoint unavailable")

    monkeypatch.setattr("retrieval.embeddings.httpx.post", unavailable)
    monkeypatch.setenv("VISIONQ_API_EMBEDDING_BACKEND", "openai-compatible")
    for key, value in {
        "BASE_URL": "http://local.invalid/v1",
        "MODEL": "fixture",
        "REVISION": "fixture-revision",
        "DIMENSIONS": "2",
    }.items():
        monkeypatch.setenv(f"VLLM_EMBEDDING_{key}", value)

    with TestClient(
        create_app(engine=object(), analytics_api_token="secret")
    ) as client:
        response = client.post(
            "/retrieval/search",
            json=request_body(),
            headers={"Authorization": "Bearer secret"},
        )
        assert response.status_code == 503
        assert response.json()["detail"] == "embedding service request failed"
