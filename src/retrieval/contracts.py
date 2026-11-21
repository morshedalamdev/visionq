"""Retrieval request and evidence contracts."""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from retrieval.chunking import ChunkConfig

_EXCLUDED_PARTS = (
    "benchmark",
    "gold",
    "grading",
    "held-out",
    "held_out",
    "questions",
    "expected-answer",
    "expected_answer",
)
_SOURCE_PATH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/ -]*$")


class CorpusDocument(BaseModel):
    key: str = Field(min_length=1, max_length=128)
    version: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=300)
    source: str = Field(min_length=1, max_length=1000)
    media_type: str = "text/markdown"
    content_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    classification: Literal["approved", "development-fixture"]
    metadata: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def source_is_safe(self) -> CorpusDocument:
        pure = PurePosixPath(self.source)
        if (
            pure.is_absolute()
            or ".." in pure.parts
            or not _SOURCE_PATH.fullmatch(self.source)
        ):
            raise ValueError("source must be a safe relative path")
        lowered = self.source.lower()
        if any(term in lowered for term in _EXCLUDED_PARTS):
            raise ValueError("source is excluded benchmark or evaluation-only material")
        return self


class CorpusManifest(BaseModel):
    format: Literal["visionq-corpus-manifest-v1"] = "visionq-corpus-manifest-v1"
    corpus_name: str = Field(min_length=1, max_length=128)
    version: int = Field(gt=0)
    evidence_kind: Literal["development-fixture", "approved"]
    documents: list[CorpusDocument] = Field(min_length=1, max_length=100)
    chunking: ChunkConfig = Field(default_factory=ChunkConfig)

    @model_validator(mode="after")
    def documents_are_consistent(self) -> CorpusManifest:
        keys = [document.key for document in self.documents]
        sources = [document.source for document in self.documents]
        if len(set(keys)) != len(keys):
            raise ValueError("document keys must be unique")
        if len(set(sources)) != len(sources):
            raise ValueError("document sources must be unique")
        if self.evidence_kind == "approved" and any(
            document.classification != "approved" for document in self.documents
        ):
            raise ValueError("approved corpus cannot contain fixture documents")
        return self


class RetrievalResult(BaseModel):
    corpus_version_id: str
    index_id: str
    chunk_id: str
    document_id: str
    document_key: str
    document_version: str
    title: str
    source_location: str
    section_title: str
    text: str
    start_character: int
    end_character: int
    document_sha256: str
    chunk_sha256: str
    score: float
    score_semantics: Literal["cosine_similarity"] = "cosine_similarity"
    embedding_backend: str
    embedding_model: str
    embedding_revision: str
    corpus_evidence_kind: str
