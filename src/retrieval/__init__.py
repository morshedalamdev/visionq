"""Versioned VisionQ document retrieval."""

from retrieval.chunking import ChunkConfig, chunk_text
from retrieval.contracts import (
    CorpusDocument,
    CorpusManifest,
    RetrievalResult,
)
from retrieval.embeddings import (
    DeterministicEmbeddingBackend,
    EmbeddingProfile,
    OpenAICompatibleEmbeddingBackend,
)
from retrieval.service import (
    CorpusConflict,
    EmbeddingCompatibilityError,
    RetrievalError,
    build_index,
    load_manifest,
    search,
    verify_index,
)

__all__ = [
    "ChunkConfig",
    "CorpusConflict",
    "CorpusDocument",
    "CorpusManifest",
    "DeterministicEmbeddingBackend",
    "EmbeddingCompatibilityError",
    "EmbeddingProfile",
    "OpenAICompatibleEmbeddingBackend",
    "RetrievalError",
    "RetrievalResult",
    "build_index",
    "chunk_text",
    "load_manifest",
    "search",
    "verify_index",
]
