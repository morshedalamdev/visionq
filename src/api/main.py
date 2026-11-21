"""VisionQ FastAPI application."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.engine import Engine

from api.analytics import router as analytics_router
from api.retrieval import router as retrieval_router
from retrieval.embeddings import EmbeddingBackend
from worker.db import database


def create_app(
    engine: Engine | None = None,
    analytics_api_token: str | None = None,
    retrieval_backend: EmbeddingBackend | None = None,
) -> FastAPI:
    owns_engine = engine is None

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        selected_engine = engine or database()
        application.state.engine = selected_engine
        try:
            yield
        finally:
            if owns_engine:
                selected_engine.dispose()

    application = FastAPI(title="VisionQ API", lifespan=lifespan)
    application.state.analytics_api_token = analytics_api_token
    application.state.retrieval_backend = retrieval_backend
    application.include_router(analytics_router)
    application.include_router(retrieval_router)
    return application


app = create_app()
