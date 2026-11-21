"""Typed read-only retrieval routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.engine import Engine

from api.analytics import engine_for, require_token
from retrieval.embeddings import EmbeddingBackend
from retrieval.service import (
    CorpusConflict,
    EmbeddingCompatibilityError,
    search,
)

router = APIRouter(prefix="/retrieval", tags=["retrieval"])


class RetrievalSearchRequest(BaseModel):
    corpus_version_id: UUID
    index_id: UUID
    query: str = Field(min_length=1, max_length=4000)
    top_k: int = Field(default=4, ge=1, le=20)

    @field_validator("query")
    @classmethod
    def nonblank_query(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must not be blank")
        return value


def backend_for(request: Request) -> EmbeddingBackend:
    backend = request.app.state.retrieval_backend
    if backend is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="retrieval embedding backend is not configured",
        )
    return backend


@router.post("/search", dependencies=[Depends(require_token)])
def search_documents(
    body: RetrievalSearchRequest,
    engine: Engine = Depends(engine_for),
    backend: EmbeddingBackend = Depends(backend_for),
) -> dict:
    try:
        return search(
            engine,
            backend,
            str(body.corpus_version_id),
            str(body.index_id),
            body.query,
            body.top_k,
        )
    except CorpusConflict as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except EmbeddingCompatibilityError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
