from __future__ import annotations

from threading import BoundedSemaphore, Event

import pytest

from mcp_server.config import settings_from_environment
from mcp_server.server import bounded_call
from mcp_server.service import MCPToolError


def test_mcp_token_configuration_fails_closed(monkeypatch):
    monkeypatch.delenv("VISIONQ_MCP_TOKEN", raising=False)
    with pytest.raises(ValueError, match="at least 24"):
        settings_from_environment()


@pytest.mark.anyio
async def test_bounded_tool_call_reports_timeout():
    def slow():
        import time

        time.sleep(0.05)
        return "late"

    with pytest.raises(Exception, match="timed out"):
        await bounded_call(slow, 0.001, "test_tool", BoundedSemaphore(1))


@pytest.mark.anyio
async def test_bounded_tool_call_preserves_safe_domain_error():
    with pytest.raises(Exception, match="invalid snapshot"):
        await bounded_call(
            lambda: (_ for _ in ()).throw(MCPToolError("invalid snapshot")),
            1,
            "test_tool",
            BoundedSemaphore(1),
        )


@pytest.mark.anyio
async def test_timeout_holds_capacity_until_the_actual_worker_exits():
    gate = BoundedSemaphore(1)
    started, release, finished = Event(), Event(), Event()

    def slow_worker():
        started.set()
        try:
            release.wait(2)
        finally:
            finished.set()

    try:
        with pytest.raises(Exception, match="timed out"):
            await bounded_call(slow_worker, 0.1, "slow", gate)
        assert started.is_set()
        with pytest.raises(Exception, match="busy"):
            await bounded_call(lambda: pytest.fail("overflow"), 1, "new", gate)
    finally:
        release.set()
    assert finished.wait(1)
    assert await bounded_call(lambda: 42, 1, "new", gate) == 42


def test_missing_mcp_backend_never_selects_development(monkeypatch):
    from mcp_server.config import embedding_from_environment

    monkeypatch.delenv("VISIONQ_MCP_EMBEDDING_BACKEND", raising=False)
    monkeypatch.setenv("VLLM_EMBEDDING_BASE_URL", "http://localhost:8100/v1")
    with pytest.raises(ValueError, match="VISIONQ_MCP_EMBEDDING_BACKEND"):
        embedding_from_environment()
