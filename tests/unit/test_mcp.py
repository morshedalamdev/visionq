from __future__ import annotations

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
        await bounded_call(slow, 0.001, "test_tool")


@pytest.mark.anyio
async def test_bounded_tool_call_preserves_safe_domain_error():
    with pytest.raises(Exception, match="invalid snapshot"):
        await bounded_call(
            lambda: (_ for _ in ()).throw(MCPToolError("invalid snapshot")),
            1,
            "test_tool",
        )
