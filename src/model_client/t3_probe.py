"""Live feasibility probe for the pinned Azure synthetic fixture."""

import asyncio
import json
import math
import os
import re
import statistics
import sys
import time
from typing import Literal

import httpx
import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from pydantic import BaseModel, ConfigDict

from mcp_server.schemas import BatchMetricsResponse, SearchDocumentsResponse

GEN = "http://vllm-gen:8000/v1/chat/completions"
MODEL = "qwen3-4b-instruct-2507"
SNAPSHOT = "ef454500-5d25-5aae-9f92-40580e1fe6a5"
BATCH = "8b1ea92d-fb87-54a0-bbf4-d7287b6f5330"
RUN = "4da3d133-6fe2-59dc-93c3-b2eb213c1730"
CORPUS = "2fad79f2-1216-5318-b1a9-8a5d9fbd7bdc"
INDEX = "eeb42ca2-b583-5f07-bc1d-0252e8b5568f"

QUESTION_TIMEOUT = 120
SHA256 = re.compile(r"[0-9a-f]{64}")

CASES = (
    ("How many images were in the batch?", "batch_image_count", 2),
    ("How many images were processed?", "processed_image_count", 2),
    ("How many boxes were predicted?", "predicted_box_count", 4),
    ("What fraction of images had predictions?", "prediction_image_ratio", 1.0),
    ("Find the document about surface scratches.", "documents", "surface-scratches"),
)


class ProbeCaseError(Exception):
    """A sanitized failure for a fixed benchmark question."""


class Plan(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    select: Literal[
        "batch_image_count",
        "processed_image_count",
        "predicted_box_count",
        "prediction_image_ratio",
        "documents",
    ]


class MetricAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    value: int | float


class DocumentAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    document_key: str


async def generate(client, schema, prompt):
    response = await client.post(
        GEN,
        json={
            "model": MODEL,
            "temperature": 0,
            "max_tokens": 32,
            "messages": [{"role": "user", "content": prompt}],
            "structured_outputs": {"json": schema.model_json_schema()},
        },
    )
    response.raise_for_status()
    payload = response.json()
    choice = payload["choices"][0]
    if payload["model"] != MODEL or choice["finish_reason"] != "stop":
        raise ValueError("Unexpected generation identity or termination")
    return schema.model_validate_json(choice["message"]["content"])


async def evidence(session, question, selection):
    if selection == "documents":
        tool = "search_documents"
        args = {
            "query": question,
            "corpus_version_id": CORPUS,
            "retrieval_index_id": INDEX,
            "top_k": 2,
        }
        schema = SearchDocumentsResponse
    else:
        tool = "get_batch_metrics"
        args = {"batch_id": BATCH, "inference_run_id": RUN, "metric_names": [selection]}
        schema = BatchMetricsResponse

    result = await session.call_tool(tool, {"snapshot_id": SNAPSHOT, **args})
    if result.is_error:
        raise ValueError(f"{tool} returned an error")
    data = schema.model_validate(result.structured_content)
    if data.snapshot_id != SNAPSHOT or not SHA256.fullmatch(data.snapshot_sha256):
        raise ValueError("Unexpected snapshot identity")

    if isinstance(data, SearchDocumentsResponse):
        if (data.corpus_version_id, data.index_id, data.query) != (
            CORPUS,
            INDEX,
            question,
        ):
            raise ValueError("Unexpected retrieval scope")
        if data.evidence_kind != "development-fixture" or len(data.results) != 2:
            raise ValueError("Expected two development fixture citations")
        first, second = data.results
        if (
            any(
                (hit.corpus_version_id, hit.index_id) != (CORPUS, INDEX)
                or hit.embedding_backend != "openai-compatible-v1"
                or hit.embedding_model != "embeddinggemma-300m"
                or hit.embedding_revision != "57c266a740f537b4dc058e1b0cda161fd15afa75"
                or not math.isfinite(hit.score)
                or not -1.000001 <= hit.score <= 1.000001
                or hit.corpus_evidence_kind != data.evidence_kind
                or not SHA256.fullmatch(hit.chunk_sha256)
                or not SHA256.fullmatch(hit.document_sha256)
                for hit in data.results
            )
            or first.score <= second.score
            or first.document_key == second.document_key
        ):
            raise ValueError("Invalid ranked retrieval evidence")
        return DocumentAnswer(document_key=first.document_key), first.model_dump()

    if len(data.metrics) != 1:
        raise ValueError("Expected exactly one metric")
    (metric,) = data.metrics
    if (
        data.scope.get("batch_id") != BATCH
        or data.scope.get("inference_run_id") != RUN
        or metric.metric_name != selection
        or metric.evidence_status != "available"
        or data.coverage.evidence_status != "available"
        or data.provenance.get("model", {}).get("evidence_kind") != "synthetic"
        or not SHA256.fullmatch(metric.definition_sha256)
    ):
        raise ValueError("Unexpected metric scope")
    return MetricAnswer(value=metric.value), {
        "snapshot_sha256": data.snapshot_sha256,
        "metric": metric.model_dump(),
    }


async def run_case(client, session, case):
    question, expected_selection, expected_value = case
    start = time.monotonic()
    async with asyncio.timeout(QUESTION_TIMEOUT):
        plan = await generate(
            client,
            Plan,
            "You are a metric and document retrieval router.\n"
            "Select exactly one option using these definitions:\n"
            "batch_image_count: total number of images in the batch.\n"
            "processed_image_count: number of images successfully processed.\n"
            "predicted_box_count: total number of predicted bounding boxes "
            "or object detections, NOT the number of images.\n"
            "prediction_image_ratio: fraction of images containing "
            "at least one prediction.\n"
            "documents: search for relevant documents or technical information.\n"
            "Match the requested entity and measurement to its definition.\n"
            f"Question: {question}",
        )
        if plan.select != expected_selection:
            raise ValueError(f"Unexpected plan for {question!r}: {plan.select}")
        expected_answer, proof = await evidence(session, question, plan.select)
        if next(iter(expected_answer.model_dump().values())) != expected_value:
            raise ValueError(f"MCP evidence disagrees with fixture for {question!r}")
        answer = await generate(
            client,
            type(expected_answer),
            f"Return the exact evidence field as JSON. Evidence: {expected_answer.model_dump_json()}",
        )
        if answer != expected_answer:
            raise ValueError(f"Generated answer disagrees with MCP for {question!r}")
    elapsed = time.monotonic() - start
    if elapsed > QUESTION_TIMEOUT:
        raise TimeoutError(f"Question exceeded 120 seconds: {question!r}")
    return {
        "question": question,
        "plan": plan.model_dump(),
        "answer": answer.model_dump(),
        "evidence": proof,
        "seconds": elapsed,
    }


async def main():
    if os.environ.get("VISIONQ_MCP_EMBEDDING_BACKEND") != "openai-compatible":
        raise ValueError("Probe requires the live MCP embedding backend")
    headers = {"Authorization": f"Bearer {os.environ['VISIONQ_MCP_TOKEN']}"}
    durations = []
    async with (
        httpx.AsyncClient(trust_env=False, timeout=120) as client,
        httpx2.AsyncClient(headers=headers, trust_env=False, timeout=120) as transport,
        streamable_http_client("http://mcp:8001/mcp", http_client=transport) as streams,
        ClientSession(streams[0], streams[1]) as session,
    ):
        async with asyncio.timeout(15):
            await session.initialize()
        for case in CASES:
            try:
                result = await run_case(client, session, case)
            except Exception as exc:
                raise ProbeCaseError(
                    f"Question failed: {case[0]} ({type(exc).__name__})"
                ) from None
            durations.append(result["seconds"])
            print(json.dumps(result, allow_nan=False), flush=True)
    print(
        json.dumps(
            {
                "questions": len(durations),
                "median_seconds": statistics.median(durations),
            }
        )
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        # Transport exceptions may include upstream response content.
        detail = str(exc) if isinstance(exc, ProbeCaseError) else type(exc).__name__
        sys.exit(f"M1.T3 probe failed: {detail}")
