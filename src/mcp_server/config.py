"""MCP service configuration and least-privilege database loading."""

from __future__ import annotations

import os
from dataclasses import dataclass

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

from retrieval.embeddings import (
    DeterministicEmbeddingBackend,
    EmbeddingBackend,
    live_backend_from_environment,
)


@dataclass(frozen=True)
class MCPSettings:
    token: str
    query_timeout_ms: int = 5_000
    tool_timeout_seconds: float = 10.0
    allowed_hosts: tuple[str, ...] = (
        "127.0.0.1",
        "127.0.0.1:*",
        "localhost",
        "localhost:*",
        "mcp",
        "mcp:*",
    )


def integer_setting(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"{name} must be an integer") from None
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def settings_from_environment() -> MCPSettings:
    token = os.environ.get("VISIONQ_MCP_TOKEN")
    if not token or len(token) < 24:
        raise ValueError("VISIONQ_MCP_TOKEN must contain at least 24 characters")
    return MCPSettings(
        token=token,
        query_timeout_ms=integer_setting(
            "VISIONQ_MCP_QUERY_TIMEOUT_MS", 5_000, 100, 120_000
        ),
        tool_timeout_seconds=integer_setting(
            "VISIONQ_MCP_TOOL_TIMEOUT_MS", 10_000, 100, 120_000
        )
        / 1000,
    )


def database_from_environment():
    raw = os.environ.get("VISIONQ_MCP_DATABASE_URL")
    if not raw:
        raise ValueError("VISIONQ_MCP_DATABASE_URL is required")
    try:
        url = make_url(raw)
    except Exception:
        raise ValueError("Invalid VISIONQ_MCP_DATABASE_URL") from None
    if url.drivername != "postgresql+psycopg" or not url.database:
        raise ValueError(
            "VISIONQ_MCP_DATABASE_URL requires postgresql+psycopg and a database"
        )
    return create_engine(url, pool_pre_ping=True)


def embedding_from_environment() -> EmbeddingBackend:
    backend = os.environ.get("VISIONQ_MCP_EMBEDDING_BACKEND")
    if backend == "deterministic":
        dimensions = integer_setting("VISIONQ_MCP_EMBEDDING_DIMENSIONS", 8, 1, 4096)
        return DeterministicEmbeddingBackend(dimensions)
    if backend != "openai-compatible":
        raise ValueError(
            "VISIONQ_MCP_EMBEDDING_BACKEND must be deterministic or openai-compatible"
        )
    return live_backend_from_environment()
