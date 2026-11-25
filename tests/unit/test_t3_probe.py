import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import ValidationError

from model_client import t3_probe as probe


def test_plan_rejects_unbounded_arguments():
    with pytest.raises(ValidationError):
        probe.Plan.model_validate({"select": "documents", "snapshot_id": "other"})


def test_plan_rejects_unknown_selection():
    with pytest.raises(ValidationError):
        probe.Plan.model_validate({"select": "compare_batches"})


def test_transport_error_surfaces():
    def unavailable(request):
        return httpx.Response(503, request=request)

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(unavailable)
        ) as client:
            with pytest.raises(httpx.HTTPStatusError):
                await probe.generate(client, probe.Plan, "question")

    asyncio.run(run())


@pytest.mark.parametrize("observed,generated", [(3, 2), (2, 3)])
def test_rejects_fixture_or_answer_mismatch(monkeypatch, observed, generated):
    case = probe.CASES[0]
    monkeypatch.setattr(
        probe,
        "evidence",
        AsyncMock(return_value=(probe.MetricAnswer(value=observed), {})),
    )
    monkeypatch.setattr(
        probe,
        "generate",
        AsyncMock(
            side_effect=[
                probe.Plan(select=case[1]),
                probe.MetricAnswer(value=generated),
            ]
        ),
    )
    with pytest.raises(ValueError, match="disagrees"):
        asyncio.run(probe.run_case(None, None, case))


def test_question_deadline_covers_mcp(monkeypatch):
    case = probe.CASES[0]
    monkeypatch.setattr(probe, "QUESTION_TIMEOUT", 0.01)
    monkeypatch.setattr(
        probe, "generate", AsyncMock(return_value=probe.Plan(select=case[1]))
    )

    async def stalled(*args):
        await asyncio.sleep(1)

    monkeypatch.setattr(probe, "evidence", stalled)
    with pytest.raises(TimeoutError):
        asyncio.run(probe.run_case(None, None, case))


def test_wrong_plan_stops_before_mcp(monkeypatch):
    monkeypatch.setattr(
        probe, "generate", AsyncMock(return_value=probe.Plan(select="documents"))
    )
    call = AsyncMock()
    monkeypatch.setattr(probe, "evidence", call)
    with pytest.raises(ValueError, match="Unexpected plan"):
        asyncio.run(probe.run_case(None, None, probe.CASES[0]))
    call.assert_not_awaited()
