"""Deterministic section-aware text chunking."""

from __future__ import annotations

import hashlib
import re
from typing import Any

from pydantic import BaseModel, Field, model_validator

from analytics.metrics import content_sha256

_TOKEN = re.compile(r"\S+")
_HEADING = re.compile(r"(?m)^#{1,6}\s+(.+?)\s*$")


class ChunkConfig(BaseModel):
    version: str = "m4t2-v1"
    chunk_size: int = Field(default=320, ge=20, le=2048)
    overlap: int = Field(default=40, ge=0, le=512)
    unit: str = "whitespace-tokens"

    @model_validator(mode="after")
    def overlap_is_smaller(self) -> ChunkConfig:
        if self.overlap >= self.chunk_size:
            raise ValueError("overlap must be smaller than chunk_size")
        if self.unit != "whitespace-tokens":
            raise ValueError("chunk unit must be whitespace-tokens")
        return self

    def fingerprint(self) -> str:
        return content_sha256(self.model_dump(mode="json"))


def _section_at(text: str, position: int) -> str:
    current = ""
    for match in _HEADING.finditer(text):
        if match.start() > position:
            break
        current = match.group(1).strip()
    return current


def chunk_text(
    document_id: str,
    text: str,
    config: ChunkConfig,
) -> list[dict[str, Any]]:
    if not isinstance(text, str):
        raise TypeError("document content must be text")
    if not text.strip():
        raise ValueError("document content is empty")
    tokens = list(_TOKEN.finditer(text))
    if not tokens:
        raise ValueError("document has no whitespace tokens")

    chunks = []
    start_token = 0
    ordinal = 0
    step = config.chunk_size - config.overlap
    while start_token < len(tokens):
        stop_token = min(start_token + config.chunk_size, len(tokens))
        start_character = tokens[start_token].start()
        end_character = tokens[stop_token - 1].end()
        chunk = text[start_character:end_character]
        section_title = _section_at(text, start_character)
        chunk_hash = content_sha256(
            {
                "document_id": document_id,
                "ordinal": ordinal,
                "start_character": start_character,
                "end_character": end_character,
                "text_sha256": hashlib.sha256(chunk.encode()).hexdigest(),
            }
        )
        chunks.append(
            {
                "ordinal": ordinal,
                "chunk_sha256": chunk_hash,
                "section_title": section_title,
                "start_character": start_character,
                "end_character": end_character,
                "text": chunk,
                "text_sha256": hashlib.sha256(chunk.encode()).hexdigest(),
            }
        )
        if stop_token == len(tokens):
            break
        start_token += step
        ordinal += 1
    return chunks
