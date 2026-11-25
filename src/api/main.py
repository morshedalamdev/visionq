"""VisionQ FastAPI application."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from starlette.types import ASGIApp, Receive, Scope, Send

from api.analytics import router as analytics_router
from api.dashboard import UPLOAD_LIMIT
from api.dashboard import router as dashboard_router
from api.retrieval import router as retrieval_router
from retrieval.embeddings import EmbeddingBackend, live_backend_from_environment
from worker.db import database

# Allow form headers and scope fields in addition to the maximum file size.
UPLOAD_BODY_LIMIT = UPLOAD_LIMIT + 64 * 1024


class UploadBodyLimit:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http" or (scope["method"], scope["path"]) != (
            "POST",
            "/app/uploads",
        ):
            return await self.app(scope, receive, send)

        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            received += len(message.get("body", b""))
            if received > UPLOAD_BODY_LIMIT:
                raise HTTPException(413, "multipart upload exceeds request size limit")
            return message

        await self.app(scope, limited_receive, send)


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
            selector = os.environ.get("VISIONQ_API_EMBEDDING_BACKEND")
            if retrieval_backend is None and selector:
                if selector != "openai-compatible":
                    raise ValueError(
                        "VISIONQ_API_EMBEDDING_BACKEND must be openai-compatible"
                    )
                application.state.retrieval_backend = live_backend_from_environment()
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

    @application.get("/ready")
    def ready() -> dict[str, str]:
        root = application.state.artifact_root
        token = analytics_api_token or os.environ.get("VISIONQ_ANALYTICS_API_TOKEN")
        if (
            not token
            or root is None
            or not root.is_dir()
            or not os.access(root, os.R_OK | os.W_OK | os.X_OK)
        ):
            raise HTTPException(503, "application configuration is unavailable")
        try:
            with application.state.engine.connect() as connection:
                connection.execute(text("SELECT id FROM image_upload_requests LIMIT 0"))
        except SQLAlchemyError:
            raise HTTPException(503, "application storage is unavailable") from None
        return {"status": "ready"}

    application.add_middleware(UploadBodyLimit)
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
