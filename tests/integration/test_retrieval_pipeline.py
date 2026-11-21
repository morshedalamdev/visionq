"""PostgreSQL pgvector retrieval, integrity and idempotent index lifecycle."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from api.main import create_app
from retrieval.embeddings import EmbeddingProfile
from retrieval.service import (
    CorpusConflict,
    EmbeddingCompatibilityError,
    build_index,
    search,
    verify_index,
)


class KeywordEmbeddingBackend:
    def __init__(
        self,
        *,
        revision: str = "1",
        dimensions: int = 3,
        model: str = "development-keywords-v1",
    ):
        self.profile = EmbeddingProfile(
            backend="keyword-development",
            model=model,
            revision=revision,
            dimensions=dimensions,
            pooling="keyword-basis",
            normalization="l2",
        )

    def _embed(self, text: str):
        weights = [
            float(text.lower().split().count("red")),
            float(text.lower().split().count("blue")),
            float(text.lower().split().count("green")),
        ]
        if not any(weights):
            weights[2] = 1.0
        if self.profile.dimensions != 3:
            return weights + [0.0] * (self.profile.dimensions - 3)
        return weights

    def embed_documents(self, texts):
        return [self._embed(text) for text in texts]

    def embed_queries(self, texts):
        return [self._embed(text) for text in texts]


def corpus_fixture(tmp_path: Path, version: int = 1, name: str = "retrieval"):
    name = f"{name}-{uuid4().hex}"
    documents = {
        "red.md": "# Color red\nred red red primary",
        "blue.md": "# Color blue\nblue blue primary",
        "green.md": "# Color green\ngreen reference",
    }
    document_rows = []
    for index, (source, content) in enumerate(documents.items()):
        (tmp_path / source).write_text(content)
        document_rows.append(
            {
                "key": source.removesuffix(".md"),
                "version": "1",
                "title": f"{source.removesuffix('.md').title()} note",
                "source": source,
                "classification": "development-fixture",
                "metadata": {"topic": "colors"},
            }
        )
    manifest = {
        "format": "visionq-corpus-manifest-v1",
        "corpus_name": name,
        "version": version,
        "evidence_kind": "development-fixture",
        "documents": document_rows,
        "chunking": {
            "version": "integration-v1",
            "chunk_size": 320,
            "overlap": 40,
            "unit": "whitespace-tokens",
        },
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    return manifest_path


def count_rows(engine, table, where="", params=None):
    with engine.connect() as connection:
        suffix = f" WHERE {where}" if where else ""
        return connection.scalar(
            text(f"SELECT count(*) FROM {table}{suffix}"), params or {}
        )


def test_exact_pgvector_search_citations_and_idempotent_rebuild(
    postgres_engine, tmp_path
):
    manifest = corpus_fixture(tmp_path)
    backend = KeywordEmbeddingBackend()

    first = build_index(postgres_engine, manifest, backend, tmp_path)
    second = build_index(postgres_engine, manifest, backend, tmp_path)

    assert first == second
    assert first["evidence_kind"] == "development-fixture"
    assert first["document_count"] == 3
    assert first["chunk_count"] == 3
    assert first["index"]["status"] == "ready"
    assert (
        count_rows(
            postgres_engine,
            "corpus_versions",
            "corpus_name = :name",
            {"name": json.loads(manifest.read_bytes())["corpus_name"]},
        )
        == 1
    )
    assert (
        count_rows(
            postgres_engine,
            "chunk_embeddings",
            "index_id = CAST(:id AS uuid)",
            {"id": first["index"]["id"]},
        )
        == 3
    )
    verification = verify_index(postgres_engine, manifest, backend)
    assert verification["ok"] is True

    response = search(
        postgres_engine,
        backend,
        first["corpus_id"],
        first["index"]["id"],
        "red",
        top_k=2,
    )
    assert response["score_semantics"] == "cosine_similarity"
    assert response["evidence_kind"] == "development-fixture"
    assert response["results"][0]["document_key"] == "red"
    assert response["results"][0]["score"] == pytest.approx(1)
    result = response["results"][0]
    assert result["source_location"] == "red.md"
    assert result["section_title"] == "Color red"
    assert result["text"] == "# Color red\nred red red primary"
    assert result["start_character"] == 0
    assert result["end_character"] == len(result["text"])
    assert len(result["document_sha256"]) == 64
    assert len(result["chunk_sha256"]) == 64


def test_authenticated_api_returns_persisted_retrieval_citations(
    postgres_engine, tmp_path
):
    manifest = corpus_fixture(tmp_path, name="api")
    backend = KeywordEmbeddingBackend()
    built = build_index(postgres_engine, manifest, backend, tmp_path)
    app = create_app(
        engine=postgres_engine,
        analytics_api_token="secret",
        retrieval_backend=backend,
    )

    with TestClient(app) as client:
        response = client.post(
            "/retrieval/search",
            headers={"Authorization": "Bearer secret"},
            json={
                "corpus_version_id": built["corpus_id"],
                "index_id": built["index"]["id"],
                "query": "blue",
                "top_k": 1,
            },
        )

    assert response.status_code == 200
    assert response.json()["results"][0]["document_key"] == "blue"
    assert response.json()["results"][0]["corpus_evidence_kind"] == (
        "development-fixture"
    )


def test_ties_are_broken_by_chunk_id_not_database_order(postgres_engine, tmp_path):
    manifest = corpus_fixture(tmp_path, name="ties")
    backend = KeywordEmbeddingBackend()
    built = build_index(postgres_engine, manifest, backend, tmp_path)

    response = search(
        postgres_engine,
        backend,
        built["corpus_id"],
        built["index"]["id"],
        "not-in-any-document",
        top_k=3,
    )
    chunk_ids = [item["chunk_id"] for item in response["results"]]

    assert chunk_ids[1:] == sorted(chunk_ids[1:])
    assert len(set(chunk_ids)) == 3


def test_interrupted_index_resumes_committed_batches(postgres_engine, tmp_path):
    manifest = corpus_fixture(tmp_path, name="resume")
    backend = KeywordEmbeddingBackend()
    interrupted = False

    def stop_after_first(stage):
        nonlocal interrupted
        if stage == "after_embedding_batch" and not interrupted:
            interrupted = True
            raise RuntimeError("simulated interruption")

    with pytest.raises(RuntimeError, match="interruption"):
        build_index(
            postgres_engine,
            manifest,
            backend,
            tmp_path,
            batch_size=1,
            hook=stop_after_first,
        )
    corpus_name = json.loads(manifest.read_bytes())["corpus_name"]
    assert (
        count_rows(
            postgres_engine,
            "chunk_embeddings",
            "index_id = (SELECT id FROM retrieval_indexes "
            "WHERE corpus_version_id = (SELECT id FROM corpus_versions "
            "WHERE corpus_name = :name))",
            {"name": corpus_name},
        )
        == 1
    )
    with postgres_engine.connect() as connection:
        status = connection.scalar(
            text("""
                SELECT ri.status
                FROM retrieval_indexes AS ri
                JOIN corpus_versions AS cv
                  ON cv.id = ri.corpus_version_id
                WHERE cv.corpus_name = :name
            """),
            {"name": corpus_name},
        )
    assert status == "failed"

    completed = build_index(
        postgres_engine,
        manifest,
        backend,
        tmp_path,
        batch_size=1,
    )
    assert completed["index"]["status"] == "ready"
    assert verify_index(postgres_engine, manifest, backend)["ok"] is True
    assert (
        count_rows(
            postgres_engine,
            "chunk_embeddings",
            "index_id = CAST(:id AS uuid)",
            {"id": completed["index"]["id"]},
        )
        == 3
    )


def test_corpus_and_embedding_profile_isolation(postgres_engine, tmp_path):
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()
    first_manifest = corpus_fixture(first_root, version=1, name="isolated")
    second_manifest = corpus_fixture(second_root, version=2, name="isolated")
    backend = KeywordEmbeddingBackend()
    first = build_index(postgres_engine, first_manifest, backend, first_root)
    second = build_index(postgres_engine, second_manifest, backend, second_root)

    assert first["corpus_id"] != second["corpus_id"]
    with pytest.raises(CorpusConflict, match="not found"):
        search(
            postgres_engine,
            backend,
            second["corpus_id"],
            first["index"]["id"],
            "red",
        )

    incompatible = KeywordEmbeddingBackend(revision="2")
    incompatible_index = build_index(
        postgres_engine, first_manifest, incompatible, first_root
    )
    assert incompatible_index["index"]["id"] != first["index"]["id"]
    with pytest.raises(EmbeddingCompatibilityError, match="profile"):
        search(
            postgres_engine,
            backend,
            first["corpus_id"],
            incompatible_index["index"]["id"],
            "red",
        )


def test_dimension_guard_rejects_wrong_pgvector_without_partial_write(
    postgres_engine, tmp_path
):
    manifest = corpus_fixture(tmp_path, name="dimensions")
    backend = KeywordEmbeddingBackend()
    built = build_index(postgres_engine, manifest, backend, tmp_path)
    with postgres_engine.connect() as connection:
        chunk_id = connection.scalar(
            text("""
                SELECT id
                FROM document_chunks
                WHERE corpus_version_id = CAST(:id AS uuid)
                ORDER BY id
                LIMIT 1
            """),
            {"id": built["corpus_id"]},
        )
    with pytest.raises(IntegrityError, match="dimension"):
        with postgres_engine.begin() as connection:
            connection.execute(
                text("""
                    INSERT INTO chunk_embeddings (
                        index_id, corpus_version_id, chunk_id,
                        vector_dimensions, embedding
                    ) VALUES (
                        CAST(:index AS uuid), CAST(:corpus AS uuid),
                        CAST(:chunk AS uuid), 4, CAST('[1,0,0,0]' AS vector)
                    )
                """),
                {
                    "index": built["index"]["id"],
                    "corpus": built["corpus_id"],
                    "chunk": str(chunk_id),
                },
            )


def test_source_change_is_explicit_and_existing_index_stays_immutable(
    postgres_engine, tmp_path
):
    manifest = corpus_fixture(tmp_path, name="drift")
    backend = KeywordEmbeddingBackend()
    built = build_index(postgres_engine, manifest, backend, tmp_path)
    before = verify_index(postgres_engine, manifest, backend)
    (tmp_path / "red.md").write_text((tmp_path / "red.md").read_text() + " changed")

    with pytest.raises(CorpusConflict, match="without a new corpus version"):
        build_index(postgres_engine, manifest, backend, tmp_path)
    assert before["ok"] is True
    assert (
        count_rows(
            postgres_engine,
            "corpus_versions",
            "corpus_name = :name",
            {"name": json.loads(manifest.read_bytes())["corpus_name"]},
        )
        == 1
    )
    assert built["index"]["status"] == "ready"


def test_corpus_documents_chunks_and_embeddings_are_immutable(
    postgres_engine, tmp_path
):
    manifest = corpus_fixture(tmp_path, name="immutable")
    backend = KeywordEmbeddingBackend()
    build_index(postgres_engine, manifest, backend, tmp_path)

    with pytest.raises(IntegrityError):
        with postgres_engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE corpus_documents SET title = 'changed' "
                    "WHERE document_key = 'red'"
                )
            )
    with pytest.raises(IntegrityError):
        with postgres_engine.begin() as connection:
            connection.execute(
                text("DELETE FROM document_chunks WHERE section_title = 'Color red'")
            )
    with pytest.raises(IntegrityError):
        with postgres_engine.begin() as connection:
            connection.execute(
                text("UPDATE chunk_embeddings SET vector_dimensions = 2")
            )


def test_index_persistence_failure_marks_failed_and_rolls_back(
    postgres_engine, tmp_path
):
    class FailingBackend(KeywordEmbeddingBackend):
        def embed_documents(self, texts):
            raise EmbeddingCompatibilityError("fixture embedding failure")

    manifest = corpus_fixture(tmp_path, name="failure")
    backend = FailingBackend()

    with pytest.raises(EmbeddingCompatibilityError, match="fixture"):
        build_index(postgres_engine, manifest, backend, tmp_path)
    corpus_name = json.loads(manifest.read_bytes())["corpus_name"]
    with postgres_engine.connect() as connection:
        state = (
            connection.execute(
                text("""
                    SELECT ri.status, ri.last_error, ri.indexed_chunks,
                           cv.status AS corpus_status
                    FROM retrieval_indexes AS ri
                    JOIN corpus_versions AS cv
                      ON cv.id = ri.corpus_version_id
                    WHERE cv.corpus_name = :name
                """),
                {"name": corpus_name},
            )
            .mappings()
            .one()
        )
    assert state["status"] == "failed"
    assert state["corpus_status"] == "failed"
    assert "EmbeddingCompatibilityError" in state["last_error"]
    assert state["indexed_chunks"] == 0
