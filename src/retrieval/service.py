"""Corpus ingestion, deterministic indexing and exact pgvector retrieval."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import text

from analytics.metrics import content_sha256
from retrieval.chunking import chunk_text
from retrieval.contracts import CorpusManifest, RetrievalResult
from retrieval.embeddings import EmbeddingBackend, normalize_vector

MAX_DOCUMENT_BYTES = 2 * 1024 * 1024
MAX_QUERY_CHARS = 4000
SnapshotHook = Callable[[str], None]


class RetrievalError(RuntimeError):
    pass


class CorpusConflict(RetrievalError, ValueError):
    pass


class EmbeddingCompatibilityError(RetrievalError, ValueError):
    pass


class IndexIntegrityError(RetrievalError):
    pass


@dataclass(frozen=True)
class PreparedDocument:
    contract: dict[str, Any]
    content: str
    content_sha256: str
    byte_count: int


@dataclass(frozen=True)
class PreparedCorpus:
    manifest: CorpusManifest
    manifest_sha256: str
    corpus_id: str
    documents: tuple[PreparedDocument, ...]
    chunks: tuple[dict[str, Any], ...]


def _identity(kind: str, value: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"visionq/retrieval/v1/{kind}/{value}"))


def _plain(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_plain(item) for item in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "hex"):
        return str(value)
    return value


def _safe_file(root: Path, source: str) -> Path:
    resolved_root = root.resolve()
    if root.is_symlink():
        raise CorpusConflict("corpus root cannot be a symlink")
    candidate = resolved_root / source
    if candidate.is_symlink():
        raise CorpusConflict(f"document is a symlink: {source}")
    path = candidate.resolve()
    if path.parent == path:
        raise CorpusConflict("document path is invalid")
    try:
        path.relative_to(resolved_root)
    except ValueError:
        raise CorpusConflict("document path escapes the corpus root") from None
    if not path.is_file():
        raise CorpusConflict(f"document is missing: {source}")
    return path


def load_manifest(
    manifest_path: Path, corpus_root: Path | None = None
) -> PreparedCorpus:
    path = Path(manifest_path)
    if path.is_symlink() or not path.is_file():
        raise CorpusConflict("corpus manifest is missing or is a symlink")
    try:
        raw = json.loads(path.read_bytes())
        manifest = CorpusManifest.model_validate(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise CorpusConflict("corpus manifest is invalid") from exc

    root = Path(corpus_root) if corpus_root is not None else path.parent
    documents = []
    document_payloads = []
    chunks = []
    content_hashes: set[str] = set()
    for ordinal, document in enumerate(manifest.documents):
        source = _safe_file(root, document.source)
        try:
            content_bytes = source.read_bytes()
        except OSError as exc:
            raise CorpusConflict(f"document cannot be read: {document.source}") from exc
        if not content_bytes or len(content_bytes) > MAX_DOCUMENT_BYTES:
            raise CorpusConflict(
                f"document must contain 1..{MAX_DOCUMENT_BYTES} bytes: "
                f"{document.source}"
            )
        try:
            content = content_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise CorpusConflict(
                f"document is not valid UTF-8: {document.source}"
            ) from exc
        checksum = hashlib.sha256(content_bytes).hexdigest()
        if checksum in content_hashes:
            raise CorpusConflict(
                f"document duplicates existing corpus content: {document.source}"
            )
        content_hashes.add(checksum)
        if document.content_sha256 is not None and document.content_sha256 != checksum:
            raise CorpusConflict(
                f"document checksum differs from manifest: {document.source}"
            )
        document_id = _identity(
            "document",
            content_sha256(
                {
                    "corpus_name": manifest.corpus_name,
                    "corpus_version": manifest.version,
                    "key": document.key,
                    "version": document.version,
                    "content_sha256": checksum,
                }
            ),
        )
        contract = document.model_dump(mode="json")
        contract["content_sha256"] = checksum
        contract["ordinal"] = ordinal
        prepared = PreparedDocument(
            contract=contract,
            content=content,
            content_sha256=checksum,
            byte_count=len(content_bytes),
        )
        documents.append(prepared)
        document_payloads.append(contract)
        for chunk in chunk_text(document_id, content, manifest.chunking):
            chunks.append(
                {
                    **chunk,
                    "id": _identity("chunk", chunk["chunk_sha256"]),
                    "document_id": document_id,
                    "document_key": document.key,
                }
            )

    resolved_manifest = {
        **manifest.model_dump(mode="json"),
        "documents": document_payloads,
        "chunk_count": len(chunks),
    }
    manifest_sha = content_sha256(resolved_manifest)
    return PreparedCorpus(
        manifest=manifest,
        manifest_sha256=manifest_sha,
        corpus_id=_identity("corpus", manifest_sha),
        documents=tuple(documents),
        chunks=tuple(chunks),
    )


def _profile_row(prepared: PreparedCorpus, backend: EmbeddingBackend) -> dict:
    profile = backend.profile
    index_id = _identity(
        "index",
        content_sha256(
            {
                "corpus_id": prepared.corpus_id,
                "profile_sha256": profile.fingerprint(),
            }
        ),
    )
    return {
        "id": index_id,
        "corpus_version_id": prepared.corpus_id,
        "profile_sha256": profile.fingerprint(),
        "embedding_backend": profile.backend,
        "embedding_model": profile.model,
        "embedding_revision": profile.revision,
        "dimensions": profile.dimensions,
        "pooling": profile.pooling,
        "normalization": profile.normalization,
        "query_prefix": profile.query_prefix,
        "document_prefix": profile.document_prefix,
        "expected_chunks": len(prepared.chunks),
    }


def _insert_corpus(connection, prepared: PreparedCorpus) -> None:
    manifest = prepared.manifest
    named = (
        connection.execute(
            text("""
                SELECT id, manifest_sha256
                FROM corpus_versions
                WHERE corpus_name = :corpus_name
                  AND version = :version
            """),
            {"corpus_name": manifest.corpus_name, "version": manifest.version},
        )
        .mappings()
        .one_or_none()
    )
    if named is not None and str(named["id"]) != prepared.corpus_id:
        raise CorpusConflict("corpus source changed without a new corpus version")
    payload = {
        **manifest.model_dump(mode="json"),
        "documents": [document.contract for document in prepared.documents],
        "chunk_count": len(prepared.chunks),
        "manifest_sha256": prepared.manifest_sha256,
    }
    connection.execute(
        text("""
            INSERT INTO corpus_versions (
                id, corpus_name, version, evidence_kind,
                manifest_sha256, manifest, chunk_config_sha256, chunk_config,
                status, expected_documents, expected_chunks, started_at
            ) VALUES (
                CAST(:id AS uuid), :corpus_name, :version, :evidence_kind,
                :manifest_sha256, CAST(:manifest AS jsonb),
                :chunk_config_sha256, CAST(:chunk_config AS jsonb),
                'indexing', :expected_documents, :expected_chunks, now()
            )
            ON CONFLICT (id) DO NOTHING
        """),
        {
            "id": prepared.corpus_id,
            "corpus_name": manifest.corpus_name,
            "version": manifest.version,
            "evidence_kind": manifest.evidence_kind,
            "manifest_sha256": prepared.manifest_sha256,
            "manifest": json.dumps(payload, allow_nan=False),
            "chunk_config_sha256": manifest.chunking.fingerprint(),
            "chunk_config": json.dumps(
                manifest.chunking.model_dump(mode="json"), allow_nan=False
            ),
            "expected_documents": len(prepared.documents),
            "expected_chunks": len(prepared.chunks),
        },
    )
    saved = (
        connection.execute(
            text("""
                SELECT manifest_sha256, chunk_config_sha256,
                       expected_documents, expected_chunks
                FROM corpus_versions
                WHERE id = CAST(:id AS uuid)
            """),
            {"id": prepared.corpus_id},
        )
        .mappings()
        .one_or_none()
    )
    if (
        saved is None
        or saved["manifest_sha256"] != prepared.manifest_sha256
        or saved["chunk_config_sha256"] != manifest.chunking.fingerprint()
        or saved["expected_documents"] != len(prepared.documents)
        or saved["expected_chunks"] != len(prepared.chunks)
    ):
        raise CorpusConflict("corpus identity already exists with different content")

    for document in prepared.documents:
        document_id = _identity(
            "document",
            content_sha256(
                {
                    "corpus_name": manifest.corpus_name,
                    "corpus_version": manifest.version,
                    "key": document.contract["key"],
                    "version": document.contract["version"],
                    "content_sha256": document.content_sha256,
                }
            ),
        )
        connection.execute(
            text("""
                INSERT INTO corpus_documents (
                    id, corpus_version_id, document_key, document_version,
                    title, source_location, content_sha256, byte_count,
                    media_type, metadata, ordinal
                ) VALUES (
                    CAST(:id AS uuid), CAST(:corpus_version_id AS uuid),
                    :document_key, :document_version, :title, :source_location,
                    :content_sha256, :byte_count, :media_type,
                    CAST(:metadata AS jsonb), :ordinal
                )
                ON CONFLICT (id) DO NOTHING
            """),
            {
                "id": document_id,
                "corpus_version_id": prepared.corpus_id,
                "document_key": document.contract["key"],
                "document_version": document.contract["version"],
                "title": document.contract["title"],
                "source_location": document.contract["source"],
                "content_sha256": document.content_sha256,
                "byte_count": document.byte_count,
                "media_type": document.contract["media_type"],
                "metadata": json.dumps(document.contract["metadata"], allow_nan=False),
                "ordinal": document.contract["ordinal"],
            },
        )
    for chunk in prepared.chunks:
        connection.execute(
            text("""
                INSERT INTO document_chunks (
                    id, corpus_version_id, document_id, ordinal,
                    section_title, start_character, end_character,
                    text, text_sha256, metadata
                ) VALUES (
                    CAST(:id AS uuid), CAST(:corpus_version_id AS uuid),
                    CAST(:document_id AS uuid), :ordinal, :section_title,
                    :start_character, :end_character, :text, :text_sha256,
                    CAST(:metadata AS jsonb)
                )
                ON CONFLICT (id) DO NOTHING
            """),
            {
                **chunk,
                "corpus_version_id": prepared.corpus_id,
                "metadata": json.dumps(
                    {
                        "document_key": chunk["document_key"],
                        "chunking_version": manifest.chunking.version,
                    },
                    allow_nan=False,
                ),
            },
        )
    actual = (
        connection.execute(
            text("""
            SELECT
                (SELECT count(*) FROM corpus_documents
                 WHERE corpus_version_id = CAST(:id AS uuid)) AS documents,
                (SELECT count(*) FROM document_chunks
                 WHERE corpus_version_id = CAST(:id AS uuid)) AS chunks
        """),
            {"id": prepared.corpus_id},
        )
        .mappings()
        .one()
    )
    if actual["documents"] != len(prepared.documents) or actual["chunks"] != len(
        prepared.chunks
    ):
        raise CorpusConflict("corpus document or chunk identity conflict")


def _insert_index(connection, prepared: PreparedCorpus, backend: EmbeddingBackend):
    row = _profile_row(prepared, backend)
    connection.execute(
        text("""
            INSERT INTO retrieval_indexes (
                id, corpus_version_id, profile_sha256, embedding_backend,
                embedding_model, embedding_revision, dimensions, pooling,
                normalization, query_prefix, document_prefix, status,
                expected_chunks, indexed_chunks, started_at
            ) VALUES (
                CAST(:id AS uuid), CAST(:corpus_version_id AS uuid),
                :profile_sha256, :embedding_backend, :embedding_model,
                :embedding_revision, :dimensions, :pooling, :normalization,
                :query_prefix, :document_prefix, 'indexing',
                :expected_chunks, 0, now()
            )
            ON CONFLICT (id) DO NOTHING
        """),
        row,
    )
    saved = (
        connection.execute(
            text("""
                SELECT profile_sha256, dimensions, embedding_backend,
                       embedding_model, embedding_revision, expected_chunks
                FROM retrieval_indexes
                WHERE id = CAST(:id AS uuid)
                  AND corpus_version_id = CAST(:corpus_version_id AS uuid)
            """),
            row,
        )
        .mappings()
        .one_or_none()
    )
    if saved is None or any(
        saved[key] != row[key]
        for key in (
            "profile_sha256",
            "dimensions",
            "embedding_backend",
            "embedding_model",
            "embedding_revision",
            "expected_chunks",
        )
    ):
        raise EmbeddingCompatibilityError(
            "embedding index identity differs from the requested profile"
        )
    connection.execute(
        text("""
            UPDATE retrieval_indexes
            SET status = 'indexing', started_at = coalesce(started_at, now()),
                finished_at = NULL, last_error = NULL
            WHERE id = CAST(:id AS uuid)
              AND status <> 'ready'
        """),
        row,
    )
    return row


def _vector_literal(values: list[float]) -> str:
    if not all(math.isfinite(value) for value in values):
        raise EmbeddingCompatibilityError(
            "embedding backend produced a non-finite vector"
        )
    return "[" + ",".join(format(value, ".17g") for value in values) + "]"


def _mark_failure(engine, index_id: str, message: str) -> None:
    safe_message = message[:500]
    with engine.begin() as connection:
        connection.execute(
            text("""
                UPDATE retrieval_indexes
                SET status = 'failed', finished_at = now(), last_error = :message
                WHERE id = CAST(:id AS uuid)
                  AND status <> 'ready'
            """),
            {"id": index_id, "message": safe_message},
        )
        connection.execute(
            text("""
                UPDATE corpus_versions
                SET status = 'failed', finished_at = now(), last_error = :message
                WHERE id = (
                    SELECT corpus_version_id
                    FROM retrieval_indexes
                    WHERE id = CAST(:id AS uuid)
                )
                  AND status <> 'ready'
            """),
            {"id": index_id, "message": safe_message},
        )


def build_index(
    engine,
    manifest_path: Path,
    backend: EmbeddingBackend,
    corpus_root: Path | None = None,
    batch_size: int = 32,
    hook: SnapshotHook | None = None,
) -> dict[str, Any]:
    if not 1 <= batch_size <= 256:
        raise ValueError("batch_size must be between 1 and 256")
    prepared = load_manifest(Path(manifest_path), corpus_root)
    profile_row = _profile_row(prepared, backend)
    with engine.begin() as connection:
        _insert_corpus(connection, prepared)
        index = _insert_index(connection, prepared, backend)
    try:
        while True:
            with engine.connect() as connection:
                missing = (
                    connection.execute(
                        text("""
                            SELECT dc.id, dc.text
                            FROM document_chunks AS dc
                            LEFT JOIN chunk_embeddings AS ce
                              ON ce.index_id = CAST(:id AS uuid)
                             AND ce.chunk_id = dc.id
                            WHERE dc.corpus_version_id =
                                  CAST(:corpus_version_id AS uuid)
                              AND ce.chunk_id IS NULL
                            ORDER BY dc.document_id, dc.ordinal
                            LIMIT :limit
                        """),
                        {**index, "limit": batch_size},
                    )
                    .mappings()
                    .all()
                )
            if not missing:
                break
            vectors = backend.embed_documents([row["text"] for row in missing])
            if len(vectors) != len(missing):
                raise EmbeddingCompatibilityError(
                    "embedding backend returned the wrong batch length"
                )
            with engine.begin() as connection:
                for row, vector in zip(missing, vectors, strict=True):
                    if len(vector) != index["dimensions"]:
                        raise EmbeddingCompatibilityError(
                            "embedding backend returned the wrong dimension"
                        )
                    normalized = (
                        normalize_vector(vector)
                        if index["normalization"] == "l2"
                        else list(vector)
                    )
                    connection.execute(
                        text("""
                            INSERT INTO chunk_embeddings (
                                index_id, corpus_version_id, chunk_id,
                                vector_dimensions, embedding
                            ) VALUES (
                                CAST(:index_id AS uuid),
                                CAST(:corpus_version_id AS uuid),
                                CAST(:chunk_id AS uuid),
                                :dimensions,
                                CAST(:embedding AS vector)
                            )
                            ON CONFLICT (index_id, chunk_id) DO NOTHING
                        """),
                        {
                            "index_id": index["id"],
                            "corpus_version_id": index["corpus_version_id"],
                            "chunk_id": str(row["id"]),
                            "dimensions": index["dimensions"],
                            "embedding": _vector_literal(normalized),
                        },
                    )
            if hook is not None:
                hook("after_embedding_batch")
        with engine.begin() as connection:
            embedded = connection.scalar(
                text("""
                    SELECT count(*)
                    FROM chunk_embeddings
                    WHERE index_id = CAST(:id AS uuid)
                      AND corpus_version_id = CAST(:corpus_version_id AS uuid)
                """),
                index,
            )
            if embedded != index["expected_chunks"]:
                raise IndexIntegrityError("index is incomplete")
            connection.execute(
                text("""
                    UPDATE retrieval_indexes
                    SET status = 'ready', indexed_chunks = :indexed_chunks,
                        finished_at = now(), last_error = NULL
                    WHERE id = CAST(:id AS uuid)
                      AND status <> 'ready'
                """),
                {**index, "indexed_chunks": embedded},
            )
            connection.execute(
                text("""
                    UPDATE corpus_versions
                    SET status = 'ready', finished_at = now(), last_error = NULL
                    WHERE id = CAST(:id AS uuid)
                      AND status <> 'ready'
                """),
                {"id": prepared.corpus_id},
            )
            profile = (
                connection.execute(
                    text("""
                        SELECT id, corpus_version_id, profile_sha256,
                               embedding_backend, embedding_model,
                               embedding_revision, dimensions, pooling,
                               normalization, query_prefix, document_prefix,
                               status, expected_chunks, indexed_chunks,
                               started_at, finished_at
                        FROM retrieval_indexes
                        WHERE id = CAST(:id AS uuid)
                    """),
                    index,
                )
                .mappings()
                .one()
            )
        return {
            "format": "visionq-retrieval-index-v1",
            "manifest_sha256": prepared.manifest_sha256,
            "corpus_id": prepared.corpus_id,
            "corpus_name": prepared.manifest.corpus_name,
            "corpus_version": prepared.manifest.version,
            "evidence_kind": prepared.manifest.evidence_kind,
            "document_count": len(prepared.documents),
            "chunk_count": len(prepared.chunks),
            "chunk_config": prepared.manifest.chunking.model_dump(mode="json"),
            "index": _plain(dict(profile)),
        }
    except Exception as exc:
        error = f"{type(exc).__name__}: indexing failed"
        try:
            _mark_failure(engine, profile_row["id"], error)
        except Exception:
            raise RetrievalError(
                "indexing failed and failure state is unresolved"
            ) from exc
        raise


def verify_index(
    engine,
    manifest_path: Path,
    backend: EmbeddingBackend,
    corpus_root: Path | None = None,
) -> dict:
    prepared = load_manifest(Path(manifest_path), corpus_root)
    index = _profile_row(prepared, backend)
    with engine.connect() as connection:
        connection = connection.execution_options(isolation_level="REPEATABLE READ")
        with connection.begin():
            corpus = (
                connection.execute(
                    text("""
                        SELECT id, manifest_sha256, expected_documents,
                               expected_chunks, status
                        FROM corpus_versions
                        WHERE id = CAST(:id AS uuid)
                    """),
                    {"id": prepared.corpus_id},
                )
                .mappings()
                .one_or_none()
            )
            saved_index = (
                connection.execute(
                    text("""
                        SELECT id, profile_sha256, dimensions, status,
                               expected_chunks, indexed_chunks
                        FROM retrieval_indexes
                        WHERE id = CAST(:id AS uuid)
                          AND corpus_version_id = CAST(:corpus_id AS uuid)
                    """),
                    {"id": index["id"], "corpus_id": prepared.corpus_id},
                )
                .mappings()
                .one_or_none()
            )
            counts = (
                connection.execute(
                    text("""
                        SELECT
                            (SELECT count(*) FROM corpus_documents
                             WHERE corpus_version_id = CAST(:id AS uuid))
                                AS documents,
                            (SELECT count(*) FROM document_chunks
                             WHERE corpus_version_id = CAST(:id AS uuid))
                                AS chunks,
                            (SELECT count(*) FROM chunk_embeddings
                             WHERE index_id = CAST(:index_id AS uuid)
                               AND corpus_version_id = CAST(:id AS uuid))
                                AS embeddings
                    """),
                    {"id": prepared.corpus_id, "index_id": index["id"]},
                )
                .mappings()
                .one()
            )
    if corpus is None or saved_index is None:
        raise IndexIntegrityError("corpus or index is missing")
    ok = (
        corpus["manifest_sha256"] == prepared.manifest_sha256
        and corpus["expected_documents"] == len(prepared.documents)
        and corpus["expected_chunks"] == len(prepared.chunks)
        and corpus["status"] == "ready"
        and saved_index["profile_sha256"] == index["profile_sha256"]
        and saved_index["dimensions"] == index["dimensions"]
        and saved_index["status"] == "ready"
        and saved_index["expected_chunks"] == len(prepared.chunks)
        and saved_index["indexed_chunks"] == len(prepared.chunks)
        and counts["documents"] == len(prepared.documents)
        and counts["chunks"] == len(prepared.chunks)
        and counts["embeddings"] == len(prepared.chunks)
    )
    return {
        "format": "visionq-retrieval-verification-v1",
        "ok": ok,
        "corpus_id": prepared.corpus_id,
        "index_id": index["id"],
        "manifest_sha256": prepared.manifest_sha256,
        "counts": dict(counts),
    }


def search(
    engine,
    backend: EmbeddingBackend,
    corpus_version_id: str,
    index_id: str,
    query: str,
    top_k: int = 4,
) -> dict[str, Any]:
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be non-empty text")
    if len(query) > MAX_QUERY_CHARS:
        raise ValueError("query is too long")
    if not 1 <= top_k <= 20:
        raise ValueError("top_k must be between 1 and 20")
    vectors = backend.embed_queries([query])
    if len(vectors) != 1:
        raise EmbeddingCompatibilityError(
            "query embedding backend returned the wrong batch length"
        )
    vector = vectors[0]
    if len(vector) != backend.profile.dimensions:
        raise EmbeddingCompatibilityError(
            "query embedding backend returned the wrong dimension"
        )
    if backend.profile.normalization == "l2":
        vector = normalize_vector(vector)
    with engine.connect() as connection:
        with connection.begin():
            index = (
                connection.execute(
                    text("""
                        SELECT ri.id, ri.corpus_version_id,
                               ri.embedding_backend, ri.embedding_model,
                               ri.embedding_revision, ri.profile_sha256,
                               cv.evidence_kind
                        FROM retrieval_indexes AS ri
                        JOIN corpus_versions AS cv
                          ON cv.id = ri.corpus_version_id
                        WHERE ri.id = CAST(:index_id AS uuid)
                          AND ri.corpus_version_id =
                              CAST(:corpus_version_id AS uuid)
                          AND ri.status = 'ready'
                          AND cv.status = 'ready'
                    """),
                    {
                        "index_id": index_id,
                        "corpus_version_id": corpus_version_id,
                    },
                )
                .mappings()
                .one_or_none()
            )
            if index is None:
                raise CorpusConflict("ready corpus index was not found")
            if (
                index["profile_sha256"] != backend.profile.fingerprint()
                or index["embedding_backend"] != backend.profile.backend
                or index["embedding_model"] != backend.profile.model
                or index["embedding_revision"] != backend.profile.revision
            ):
                raise EmbeddingCompatibilityError(
                    "query embedding profile differs from the selected index"
                )
            rows = (
                connection.execute(
                    text("""
                        SELECT
                            CAST(dc.id AS text) AS chunk_id,
                            CAST(cd.id AS text) AS document_id,
                            cd.document_key, cd.document_version, cd.title,
                            cd.source_location, cd.content_sha256,
                            dc.section_title, dc.start_character, dc.end_character,
                            dc.text, dc.text_sha256,
                            (1 - (ce.embedding <=> CAST(:vector AS vector)))
                                AS score
                        FROM chunk_embeddings AS ce
                        JOIN document_chunks AS dc
                          ON dc.id = ce.chunk_id
                         AND dc.corpus_version_id = ce.corpus_version_id
                        JOIN corpus_documents AS cd
                          ON cd.id = dc.document_id
                         AND cd.corpus_version_id = dc.corpus_version_id
                        WHERE ce.index_id = CAST(:index_id AS uuid)
                          AND ce.corpus_version_id =
                              CAST(:corpus_version_id AS uuid)
                        ORDER BY ce.embedding <=> CAST(:vector AS vector),
                                 dc.id
                        LIMIT :top_k
                    """),
                    {
                        "index_id": index_id,
                        "corpus_version_id": corpus_version_id,
                        "vector": _vector_literal(vector),
                        "top_k": top_k,
                    },
                )
                .mappings()
                .all()
            )
    results = [
        RetrievalResult(
            corpus_version_id=corpus_version_id,
            index_id=index_id,
            corpus_evidence_kind=index["evidence_kind"],
            document_sha256=row["content_sha256"],
            chunk_sha256=row["text_sha256"],
            **{
                key: value
                for key, value in _plain(dict(row)).items()
                if key not in ("content_sha256", "text_sha256")
            },
            embedding_backend=index["embedding_backend"],
            embedding_model=index["embedding_model"],
            embedding_revision=index["embedding_revision"],
        )
        for row in rows
    ]
    return {
        "format": "visionq-retrieval-results-v1",
        "query": query,
        "corpus_version_id": corpus_version_id,
        "index_id": index_id,
        "top_k": top_k,
        "score_semantics": "cosine_similarity",
        "evidence_kind": index["evidence_kind"],
        "results": [result.model_dump(mode="json") for result in results],
    }
