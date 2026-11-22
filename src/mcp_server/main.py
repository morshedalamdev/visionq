"""VisionQ MCP Streamable HTTP process entry point."""

from __future__ import annotations

import os

import uvicorn

from mcp_server.config import (
    database_from_environment,
    embedding_from_environment,
    settings_from_environment,
)
from mcp_server.server import create_mcp_app


def build_app():
    settings = settings_from_environment()
    engine = database_from_environment()
    backend = embedding_from_environment()
    return create_mcp_app(engine, backend, settings)


def run() -> None:
    host = os.environ.get("VISIONQ_MCP_HOST", "127.0.0.1")
    port = int(os.environ.get("VISIONQ_MCP_PORT", "8001"))
    uvicorn.run(build_app(), host=host, port=port, log_level="info")


if __name__ == "__main__":
    run()
