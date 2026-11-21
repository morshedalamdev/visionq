"""VisionQ FastAPI application."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.engine import Engine

from api.analytics import router
from worker.db import database


def create_app(
    engine: Engine | None = None,
    analytics_api_token: str | None = None,
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
    application.include_router(router)
    return application


app = create_app()
