from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from retrieval.chunking import ChunkConfig, chunk_text
from retrieval.contracts import CorpusManifest
from retrieval.embeddings import (
    DeterministicEmbeddingBackend,
    OpenAICompatibleEmbeddingBackend,
)
from retrieval.service import CorpusConflict, load_manifest


def manifest(document=None):
    return {
        "format": "visionq-corpus-manifest-v1",
        "corpus_name": "visionq-development-docs",
        "version": 1,
        "evidence_kind": "development-fixture",
        "documents": [
            document
            or {
                "key": "pipeline",
                "version": "1",
                "title": "Pipeline",
                "source": "pipeline.md",
                "classification": "development-fixture",
            }
        ],
        "chunking": {
            "version": "test-v1",
            "chunk_size": 20,
            "overlap": 5,
            "unit": "whitespace-tokens",
        },
    }


def write_manifest(
    tmp_path: Path,
    body=None,
    content=" ".join(f"word{index}" for index in range(30)),
):
    (tmp_path / "pipeline.md").write_text(content)
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(body or manifest()))
    return path


def test_chunking_is_stable_section_aware_and_exactly_overlaps():
    text = "# Overview\none two three four five six seven eight nine ten"
    config = ChunkConfig(chunk_size=20, overlap=5)

    first = chunk_text("document", text, config)
    second = chunk_text("document", text, config)

    assert first == second
    assert len(first) == 1
    assert first[0]["section_title"] == "Overview"
    long_text = text + " " + " ".join(f"word{index}" for index in range(40))
    long_chunks = chunk_text("document", long_text, config)
    assert len(long_chunks) > 1
    overlap = set(long_chunks[0]["text"].split()) & set(long_chunks[1]["text"].split())
    assert overlap
    assert all(item["start_character"] < item["end_character"] for item in first)
    assert all(
        text[item["start_character"] : item["end_character"]] == item["text"]
        for item in first
    )
    assert len({item["chunk_sha256"] for item in first}) == len(first)


def test_chunking_rejects_empty_content_and_invalid_overlap():
    with pytest.raises(ValueError, match="empty"):
        chunk_text("document", "  \n", ChunkConfig())
    with pytest.raises(ValidationError, match="overlap"):
        ChunkConfig(chunk_size=20, overlap=20)


def test_deterministic_embedding_is_finite_normalized_and_repeatable():
    backend = DeterministicEmbeddingBackend(dimensions=8)

    first = backend.embed_documents(["surface defect glossary"])
    second = backend.embed_documents(["surface defect glossary"])
    query = backend.embed_queries(["surface defect"])[0]

    assert first == second
    assert len(first[0]) == 8
    assert sum(value * value for value in first[0]) == pytest.approx(1)
    assert len(query) == 8


def test_deterministic_embedding_dimension_is_part_of_profile():
    short = DeterministicEmbeddingBackend(dimensions=4)
    long = DeterministicEmbeddingBackend(dimensions=8)

    assert len(short.embed_queries(["query"])[0]) == 4
    assert len(long.embed_queries(["query"])[0]) == 8
    assert short.profile.fingerprint() != long.profile.fingerprint()


def test_openai_adapter_preserves_indexes_dimensions_and_prefixes(monkeypatch):
    sent = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "data": [
                    {"index": 1, "embedding": [0.0, 1.0]},
                    {"index": 0, "embedding": [1.0, 0.0]},
                ]
            }

    def fake_post(url, json, timeout):
        sent.update(url=url, body=json, timeout=timeout)
        return Response()

    monkeypatch.setattr("retrieval.embeddings.httpx.post", fake_post)
    backend = OpenAICompatibleEmbeddingBackend(
        "http://localhost:8100/v1",
        "embedding-model",
        "revision-1",
        2,
        query_prefix="query: ",
        document_prefix="document: ",
        timeout=5,
    )

    result = backend.embed_queries(["one", "two"])

    assert result == [[1.0, 0.0], [0.0, 1.0]]
    assert sent["url"] == "http://localhost:8100/v1/embeddings"
    assert sent["body"] == {
        "model": "embedding-model",
        "input": ["query: one", "query: two"],
    }
    assert sent["timeout"] == 5


def test_openai_adapter_rejects_incomplete_or_wrong_dimension(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "data": [
                    {"index": 0, "embedding": [1.0]},
                ]
            }

    monkeypatch.setattr(
        "retrieval.embeddings.httpx.post", lambda *args, **kwargs: Response()
    )
    backend = OpenAICompatibleEmbeddingBackend(
        "http://localhost:8100/v1",
        "embedding-model",
        "revision-1",
        2,
    )

    with pytest.raises(ValueError, match="dimension"):
        backend.embed_documents(["text"])


def test_manifest_rejects_duplicate_sources_and_excluded_materials():
    body = manifest()
    body["documents"].append({**body["documents"][0], "key": "other", "title": "Other"})
    with pytest.raises(ValidationError, match="unique"):
        CorpusManifest.model_validate(body)

    excluded = manifest()
    excluded["documents"][0]["source"] = "benchmark/gold-answers.md"
    with pytest.raises(ValidationError, match="excluded"):
        CorpusManifest.model_validate(excluded)

    traversal = manifest()
    traversal["documents"][0]["source"] = "../secret.md"
    with pytest.raises(ValidationError, match="safe relative path"):
        CorpusManifest.model_validate(traversal)


def test_load_manifest_rejects_duplicate_content(tmp_path):
    body = manifest()
    body["documents"].append(
        {
            "key": "duplicate",
            "version": "1",
            "title": "Duplicate",
            "source": "duplicate.md",
            "classification": "development-fixture",
        }
    )
    (tmp_path / "pipeline.md").write_text("identical content")
    (tmp_path / "duplicate.md").write_text("identical content")
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(body))

    with pytest.raises(CorpusConflict, match="duplicates existing"):
        load_manifest(path, tmp_path)


def test_approved_corpus_cannot_contain_fixture_documents():
    body = manifest()
    body["evidence_kind"] = "approved"

    with pytest.raises(ValidationError, match="fixture"):
        CorpusManifest.model_validate(body)


def test_load_manifest_is_repeatable_and_detects_source_drift(tmp_path):
    path = write_manifest(tmp_path)
    first = load_manifest(path, tmp_path)
    second = load_manifest(path, tmp_path)

    assert first.manifest_sha256 == second.manifest_sha256
    assert first.corpus_id == second.corpus_id
    assert len(first.chunks) == 2
    assert len({chunk["id"] for chunk in first.chunks}) == len(first.chunks)

    body = json.loads(path.read_bytes())
    body["documents"][0]["content_sha256"] = "0" * 64
    path.write_text(json.dumps(body))
    with pytest.raises(CorpusConflict, match="checksum differs"):
        load_manifest(path, tmp_path)


def test_load_manifest_rejects_symlink_source(tmp_path):
    path = write_manifest(tmp_path)
    (tmp_path / "pipeline.md").unlink()
    (tmp_path / "pipeline.md").symlink_to(path)

    with pytest.raises(CorpusConflict, match="symlink"):
        load_manifest(path, tmp_path)


def test_content_hash_uses_exact_utf8_bytes(tmp_path):
    content = "VisionQ λ\n"
    body = manifest()
    body["documents"][0]["content_sha256"] = hashlib.sha256(
        content.encode()
    ).hexdigest()
    path = write_manifest(tmp_path, body, content)

    prepared = load_manifest(path, tmp_path)

    assert (
        prepared.documents[0].content_sha256
        == hashlib.sha256(content.encode()).hexdigest()
    )


def test_manifest_load_rejects_invalid_utf8(tmp_path):
    path = write_manifest(tmp_path)
    (tmp_path / "pipeline.md").write_bytes(b"\xff")

    with pytest.raises(CorpusConflict, match="UTF-8"):
        load_manifest(path, tmp_path)
