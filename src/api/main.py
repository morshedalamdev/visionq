"""VisionQ FastAPI application."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.engine import Engine

from api.analytics import router as analytics_router
from api.dashboard import router as dashboard_router
from api.retrieval import router as retrieval_router
from retrieval.embeddings import EmbeddingBackend
from worker.db import database


def create_app(
    engine: Engine | None = None,
    analytics_api_token: str | None = None,
    retrieval_backend: EmbeddingBackend | None = None,
    artifact_root: Path | None = None,
) -> FastAPI:
    owns_engine = engine is None

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        selected_engine = engine or database()
        application.state.engine = selected_engine
        selected_root = artifact_root or (
            Path(os.environ["ARTIFACT_ROOT"])
            if os.environ.get("ARTIFACT_ROOT")
            else None
        )
        application.state.artifact_root = selected_root
        try:
            yield
        finally:
            if owns_engine:
                selected_engine.dispose()

    application = FastAPI(title="VisionQ API", lifespan=lifespan)
    if engine is not None:
        application.state.engine = engine
    application.state.analytics_api_token = analytics_api_token
    application.state.retrieval_backend = retrieval_backend
    application.state.artifact_root = artifact_root

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    application.add_middleware(
        CORSMiddleware,
        allow_origins=[
            origin.strip()
            for origin in os.environ.get(
                "VISIONQ_UI_ORIGINS",
                "http://127.0.0.1:5173,http://localhost:5173",
            ).split(",")
            if origin.strip()
        ],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )
    application.include_router(analytics_router)
    application.include_router(retrieval_router)
    application.include_router(dashboard_router)
    return application


app = create_app()
