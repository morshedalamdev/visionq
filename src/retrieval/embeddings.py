"""Model-independent embedding profiles and adapters."""

from __future__ import annotations

import hashlib
import math
import os
from collections.abc import Sequence
from typing import Protocol

import httpx
from pydantic import BaseModel, Field

from analytics.metrics import content_sha256


class EmbeddingProfile(BaseModel):
    backend: str = Field(min_length=1, max_length=128)
    model: str = Field(min_length=1, max_length=512)
    revision: str = Field(min_length=1, max_length=128)
    dimensions: int = Field(gt=0, le=4096)
    pooling: str = Field(default="mean", min_length=1, max_length=128)
    normalization: str = Field(default="l2", pattern=r"^(none|l2)$")
    query_prefix: str = ""
    document_prefix: str = ""

    def fingerprint(self) -> str:
        return content_sha256(self.model_dump(mode="json"))


class EmbeddingBackend(Protocol):
    profile: EmbeddingProfile

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...

    def embed_queries(self, texts: Sequence[str]) -> list[list[float]]: ...


def validate_vector(vector: Sequence[float], dimensions: int) -> list[float]:
    if len(vector) != dimensions:
        raise ValueError(
            f"embedding dimension {len(vector)} differs from expected {dimensions}"
        )
    result = [float(value) for value in vector]
    if not all(math.isfinite(value) for value in result):
        raise ValueError("embedding contains a non-finite value")
    if not any(result):
        raise ValueError("embedding vector is all zero")
    return result


def normalize_vector(vector: Sequence[float]) -> list[float]:
    values = list(vector)
    norm = math.sqrt(sum(value * value for value in values))
    if norm == 0:
        raise ValueError("embedding vector is all zero")
    return [value / norm for value in values]


class DeterministicEmbeddingBackend:
    """Labeled development-only embeddings derived from stable text features."""

    def __init__(self, dimensions: int = 8):
        self.profile = EmbeddingProfile(
            backend="deterministic-development",
            model="visionq-hash-unigram-v1",
            revision="1",
            dimensions=dimensions,
            pooling="signed-hash-unigrams",
            normalization="l2",
        )

    def _embed(self, texts: Sequence[str], prefix: str) -> list[list[float]]:
        vectors = []
        for text in texts:
            vector = [0.0] * self.profile.dimensions
            for token in (prefix + text).casefold().split():
                digest = hashlib.sha256(token.encode()).digest()
                index = int.from_bytes(digest[:4], "big") % len(vector)
                vector[index] += 1.0 if digest[4] & 1 else -1.0
            if not any(vector):
                fallback = hashlib.sha256((prefix + text).encode()).digest()
                vector[int.from_bytes(fallback[:4], "big") % len(vector)] = 1.0
            vectors.append(
                normalize_vector(validate_vector(vector, self.profile.dimensions))
            )
        return vectors

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return self._embed(texts, self.profile.document_prefix)

    def embed_queries(self, texts: Sequence[str]) -> list[list[float]]:
        return self._embed(texts, self.profile.query_prefix)


class EmbeddingServiceError(RuntimeError, ValueError):
    """The selected embedding endpoint could not fulfill its contract."""


class OpenAICompatibleEmbeddingBackend:
    """Private vLLM/OpenAI-compatible embedding adapter."""

    def __init__(
        self,
        base_url: str,
        model: str,
        revision: str,
        dimensions: int,
        query_prefix: str = "",
        document_prefix: str = "",
        timeout: float = 30.0,
    ):
        normalized_url = base_url.rstrip("/")
        if not normalized_url.startswith("http://") and not normalized_url.startswith(
            "https://"
        ):
            raise ValueError("embedding base URL must use http or https")
        if timeout <= 0:
            raise ValueError("embedding timeout must be positive")
        self._base_url = normalized_url
        self._timeout = timeout
        self.profile = EmbeddingProfile(
            backend="openai-compatible-v1",
            model=model,
            revision=revision,
            dimensions=dimensions,
            pooling="service",
            normalization="none",
            query_prefix=query_prefix,
            document_prefix=document_prefix,
        )

    def _embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            response = httpx.post(
                f"{self._base_url}/embeddings",
                json={"model": self.profile.model, "input": list(texts)},
                timeout=self._timeout,
            )
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise EmbeddingServiceError("embedding service request failed") from exc
        if (
            isinstance(body, dict)
            and "model" in body
            and body["model"] != self.profile.model
        ):
            raise EmbeddingServiceError("embedding service returned a different model")
        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, list) or len(data) != len(texts):
            raise EmbeddingServiceError("embedding service returned incomplete data")
        if any(
            not isinstance(item, dict) or type(item.get("index")) is not int
            for item in data
        ):
            raise EmbeddingServiceError("embedding service returned invalid indexes")
        ordered = sorted(data, key=lambda item: item["index"])
        vectors = []
        for expected_index, item in enumerate(ordered):
            if item["index"] != expected_index:
                raise EmbeddingServiceError(
                    "embedding service returned invalid indexes"
                )
            raw = item.get("embedding")
            if not isinstance(raw, list):
                raise EmbeddingServiceError(
                    "embedding service returned an invalid vector"
                )
            try:
                vectors.append(validate_vector(raw, self.profile.dimensions))
            except (TypeError, ValueError, OverflowError) as exc:
                raise EmbeddingServiceError(
                    f"embedding service returned an invalid vector: {exc}"
                ) from exc
        return vectors

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        prefixed = [self.profile.document_prefix + text for text in texts]
        return self._embed(prefixed)

    def embed_queries(self, texts: Sequence[str]) -> list[list[float]]:
        prefixed = [self.profile.query_prefix + text for text in texts]
        return self._embed(prefixed)


def live_backend_from_environment() -> OpenAICompatibleEmbeddingBackend:
    required = (
        "VLLM_EMBEDDING_BASE_URL",
        "VLLM_EMBEDDING_MODEL",
        "VLLM_EMBEDDING_REVISION",
        "VLLM_EMBEDDING_DIMENSIONS",
    )
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise ValueError(f"missing embedding configuration: {', '.join(missing)}")
    dimensions = int(os.environ["VLLM_EMBEDDING_DIMENSIONS"])
    return OpenAICompatibleEmbeddingBackend(
        os.environ["VLLM_EMBEDDING_BASE_URL"],
        os.environ["VLLM_EMBEDDING_MODEL"],
        os.environ["VLLM_EMBEDDING_REVISION"],
        dimensions,
        query_prefix=os.environ.get("VLLM_EMBEDDING_QUERY_PREFIX", ""),
        document_prefix=os.environ.get("VLLM_EMBEDDING_DOCUMENT_PREFIX", ""),
    )
