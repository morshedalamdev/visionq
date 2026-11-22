"""Actual MCP Streamable HTTP integration against PostgreSQL/pgvector."""

from __future__ import annotations

import asyncio
import socket
import threading
import time
from contextlib import asynccontextmanager
from uuid import uuid4

import httpx2
import pytest
import uvicorn
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp_support import (
    add_quality_issue,
    analytics_scope,
    build_corpus,
    build_inference_scope,
    prediction,
    run_scope,
)
from sqlalchemy import create_engine, text

from analytics.service import capture_context_snapshot
from mcp_server.config import MCPSettings
from mcp_server.server import create_mcp_app, create_mcp_server
from retrieval.embeddings import DeterministicEmbeddingBackend
from retrieval.service import build_index
from worker.inference import run_inference


@pytest.fixture
def anyio_backend():
    return "asyncio"


class FixedEmbeddingBackend(DeterministicEmbeddingBackend):
    def __init__(self):
        super().__init__(dimensions=8)


def table_counts(engine):
    with engine.connect() as connection:
        return {
            table: connection.scalar(text(f"SELECT count(*) FROM {table}"))
            for table in (
                "analytics_snapshots",
                "corpus_versions",
                "retrieval_indexes",
                "chunk_embeddings",
            )
        }


@asynccontextmanager
async def serve(app):
    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    port = listener.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=port,
            log_level="warning",
            lifespan="on",
        )
    )

    def run():
        asyncio.run(server.serve(sockets=[listener]))

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and time.monotonic() < deadline:
        await asyncio.sleep(0.01)
    if not server.started:
        server.should_exit = True
        thread.join(timeout=5)
        raise RuntimeError("MCP test server did not start")
    try:
        yield f"http://127.0.0.1:{port}/mcp"
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        if thread.is_alive():
            raise RuntimeError("MCP test server did not stop")


async def connect(url: str, token: str):
    http = httpx2.AsyncClient(
        headers={"Authorization": f"Bearer {token}"},
        timeout=httpx2.Timeout(5.0, read=10.0),
    )
    await http.__aenter__()
    transport = streamable_http_client(url, http_client=http)
    client = Client(transport)
    await client.__aenter__()
    return http, client


async def disconnect(http, client):
    await client.__aexit__(None, None, None)
    await http.__aexit__(None, None, None)


@pytest.mark.anyio
async def test_actual_streamable_http_discovers_and_calls_exactly_five_tools(
    postgres_engine, tmp_path
):
    fixture = build_inference_scope(postgres_engine, tmp_path, "mcp")
    left_run = run_scope(fixture, "cpu", lambda *args: [])
    right_run = run_scope(fixture, "mps", prediction)
    backend = FixedEmbeddingBackend()
    manifest = build_corpus(tmp_path)
    indexed = build_index(
        postgres_engine,
        manifest,
        backend,
        manifest.parent,
    )
    asset_id = None
    with postgres_engine.connect() as connection:
        asset_id = connection.scalar(
            text("""
                SELECT asset_id
                FROM batch_items
                WHERE batch_id = CAST(:batch AS uuid)
                ORDER BY ordinal
                LIMIT 1
            """),
            {"batch": fixture["batch"]["batch_id"]},
        )
    add_quality_issue(
        postgres_engine,
        fixture["batch"]["dataset_version_id"],
        str(asset_id),
        "mcp-captured-error",
    )
    snapshot = capture_context_snapshot(
        postgres_engine,
        [
            ("left", analytics_scope(fixture, left_run)),
            ("right", analytics_scope(fixture, right_run)),
        ],
        [
            "batch_image_count",
            "processed_image_count",
            "predicted_box_count",
            "prediction_image_ratio",
        ],
        indexed["corpus_id"],
        indexed["index"]["id"],
    )
    before = table_counts(postgres_engine)
    token = "mcp-integration-token-24-characters"
    app = create_mcp_app(
        postgres_engine,
        backend,
        MCPSettings(
            token=token,
            query_timeout_ms=2_000,
            tool_timeout_seconds=5,
        ),
    )

    async with serve(app) as url:
        http, client = await connect(url, token)
        try:
            listed = await client.list_tools()
            assert sorted(tool.name for tool in listed.tools) == sorted(
                [
                    "get_batch_metrics",
                    "compare_batches",
                    "get_quality_report",
                    "get_run_provenance",
                    "search_documents",
                ]
            )

            common = {
                "snapshot_id": snapshot["id"],
                "metric_names": [
                    "batch_image_count",
                    "predicted_box_count",
                ],
            }
            metrics = await client.call_tool(
                "get_batch_metrics",
                {
                    **common,
                    "batch_id": fixture["batch"]["batch_id"],
                    "inference_run_id": right_run,
                },
            )
            comparison = await client.call_tool(
                "compare_batches",
                {
                    "snapshot_id": snapshot["id"],
                    "left_batch_id": fixture["batch"]["batch_id"],
                    "left_inference_run_id": left_run,
                    "right_batch_id": fixture["batch"]["batch_id"],
                    "right_inference_run_id": right_run,
                    "metric_names": ["predicted_box_count"],
                },
            )
            quality = await client.call_tool(
                "get_quality_report",
                {
                    "snapshot_id": snapshot["id"],
                    "dataset_version_id": fixture["batch"]["dataset_version_id"],
                    "batch_id": fixture["batch"]["batch_id"],
                },
            )
            provenance = await client.call_tool(
                "get_run_provenance",
                {
                    "snapshot_id": snapshot["id"],
                    "inference_run_id": right_run,
                },
            )
            retrieval = await client.call_tool(
                "search_documents",
                {
                    "snapshot_id": snapshot["id"],
                    "query": "metrics ratio denominator",
                    "corpus_version_id": indexed["corpus_id"],
                    "retrieval_index_id": indexed["index"]["id"],
                    "top_k": 2,
                },
            )

            assert metrics.is_error is False
            assert comparison.is_error is False
            assert quality.is_error is False
            assert provenance.is_error is False
            assert retrieval.is_error is False
            assert comparison.structured_content["compatibility_status"] == (
                "compatible"
            )
            assert quality.structured_content["finding_count"] > 0
            assert any(
                finding["rule_id"] == "mcp-captured-error"
                for finding in quality.structured_content["findings"]
            )
            assert (
                provenance.structured_content["evaluation_links"]["available"] is False
            )
            assert (
                retrieval.structured_content["results"][0]["corpus_evidence_kind"]
                == "development-fixture"
            )

            oversized = await client.call_tool(
                "search_documents",
                {
                    "snapshot_id": snapshot["id"],
                    "query": "metrics",
                    "corpus_version_id": indexed["corpus_id"],
                    "retrieval_index_id": indexed["index"]["id"],
                    "top_k": 5,
                },
            )
            wrong_metric = await client.call_tool(
                "get_batch_metrics",
                {
                    **common,
                    "batch_id": fixture["batch"]["batch_id"],
                    "inference_run_id": right_run,
                    "metric_names": ["invented_accuracy"],
                },
            )
            missing_snapshot = await client.call_tool(
                "get_run_provenance",
                {
                    "snapshot_id": str(uuid4()),
                    "inference_run_id": right_run,
                },
            )
            mismatched_corpus = await client.call_tool(
                "search_documents",
                {
                    "snapshot_id": snapshot["id"],
                    "query": "metrics",
                    "corpus_version_id": str(uuid4()),
                    "retrieval_index_id": indexed["index"]["id"],
                    "top_k": 1,
                },
            )
            wrong_class = await client.call_tool(
                "get_batch_metrics",
                {
                    **common,
                    "batch_id": fixture["batch"]["batch_id"],
                    "inference_run_id": right_run,
                    "class_id": 5,
                },
            )
            assert oversized.is_error is True
            assert wrong_metric.is_error is True
            assert missing_snapshot.is_error is True
            assert mismatched_corpus.is_error is True
            assert wrong_class.is_error is True
        finally:
            await disconnect(http, client)

    assert table_counts(postgres_engine) == before


@pytest.mark.anyio
async def test_bearer_auth_is_required_for_streamable_http(postgres_engine):
    app = create_mcp_app(
        postgres_engine,
        FixedEmbeddingBackend(),
        MCPSettings(token="mcp-integration-token-24-characters"),
    )
    async with serve(app) as url:
        async with httpx2.AsyncClient() as client:
            response = await client.post(url, json={"jsonrpc": "2.0"})
        assert response.status_code == 401


@pytest.mark.anyio
async def test_snapshot_answers_do_not_change_after_quality_insert(
    postgres_engine, tmp_path
):
    fixture = build_inference_scope(postgres_engine, tmp_path, "immutable-mcp")
    run_id = run_scope(fixture, "cpu", lambda *args: [])
    with postgres_engine.connect() as connection:
        asset_id = connection.scalar(
            text("""
                SELECT asset_id
                FROM batch_items
                WHERE batch_id = CAST(:batch AS uuid)
                ORDER BY ordinal
                LIMIT 1
            """),
            {"batch": fixture["batch"]["batch_id"]},
        )
    snapshot = capture_context_snapshot(
        postgres_engine,
        [("primary", analytics_scope(fixture, run_id))],
    )
    add_quality_issue(
        postgres_engine,
        fixture["batch"]["dataset_version_id"],
        str(asset_id),
        "late-mutable-insert",
    )
    server = create_mcp_server(
        postgres_engine,
        FixedEmbeddingBackend(),
        MCPSettings(token="mcp-integration-token-24-characters"),
    )
    async with Client(server) as client:
        quality = await client.call_tool(
            "get_quality_report",
            {
                "snapshot_id": snapshot["id"],
                "dataset_version_id": fixture["batch"]["dataset_version_id"],
                "batch_id": fixture["batch"]["batch_id"],
            },
        )

    assert quality.is_error is False
    captured = quality.structured_content
    assert captured["finding_count"] > 0
    assert all(
        finding["rule_id"] != "late-mutable-insert" for finding in captured["findings"]
    )


@pytest.mark.anyio
async def test_database_outage_is_an_explicit_tool_failure(postgres_engine):
    from sqlalchemy import create_engine

    unavailable = create_engine(
        "postgresql+psycopg://visionq:wrong@127.0.0.1:1/visionq",
        pool_pre_ping=True,
        connect_args={"connect_timeout": 1},
    )
    server = create_mcp_server(
        unavailable,
        FixedEmbeddingBackend(),
        MCPSettings(
            token="mcp-integration-token-24-characters",
            query_timeout_ms=100,
            tool_timeout_seconds=0.2,
        ),
    )
    async with Client(server) as client:
        result = await client.call_tool(
            "get_run_provenance",
            {
                "snapshot_id": str(uuid4()),
                "inference_run_id": str(uuid4()),
            },
        )
    unavailable.dispose()

    assert result.is_error is True
    assert "storage is unavailable" in result.content[0].text


@pytest.mark.anyio
async def test_partial_pending_and_failed_states_are_preserved(
    postgres_engine, tmp_path
):
    fixture = build_inference_scope(postgres_engine, tmp_path, "states-mcp")
    interrupted = False

    def stop_after_commit(stage, asset_id):
        nonlocal interrupted
        if stage == "after_item_commit" and not interrupted:
            interrupted = True
            raise RuntimeError("simulated interruption")

    with pytest.raises(RuntimeError, match="interruption"):
        run_inference(
            postgres_engine,
            fixture["root"],
            fixture["batch"]["batch_id"],
            fixture["model"]["id"],
            "cpu",
            predictor=lambda *args: [],
            hook=stop_after_commit,
        )
    with postgres_engine.connect() as connection:
        partial_run = connection.scalar(
            text("""
                SELECT id
                FROM inference_runs
                WHERE batch_id = CAST(:batch AS uuid)
                  AND config->>'device' = 'cpu'
            """),
            {"batch": fixture["batch"]["batch_id"]},
        )
    failed = run_inference(
        postgres_engine,
        fixture["root"],
        fixture["batch"]["batch_id"],
        fixture["model"]["id"],
        "mps",
        predictor=lambda *args: [{"cls": 0, "conf": 2, "box": [0, 0, 1, 1]}],
    )
    snapshot = capture_context_snapshot(
        postgres_engine,
        [
            ("left", analytics_scope(fixture, str(partial_run))),
            ("right", analytics_scope(fixture, failed["run_id"])),
        ],
        [
            "pending_image_count",
            "failed_image_count",
            "prediction_image_ratio",
        ],
    )
    server = create_mcp_server(
        postgres_engine,
        FixedEmbeddingBackend(),
        MCPSettings(token="mcp-integration-token-24-characters"),
    )
    async with Client(server) as client:
        partial = await client.call_tool(
            "get_batch_metrics",
            {
                "snapshot_id": snapshot["id"],
                "batch_id": fixture["batch"]["batch_id"],
                "inference_run_id": str(partial_run),
                "metric_names": [
                    "pending_image_count",
                    "prediction_image_ratio",
                ],
            },
        )
        failed_result = await client.call_tool(
            "get_batch_metrics",
            {
                "snapshot_id": snapshot["id"],
                "batch_id": fixture["batch"]["batch_id"],
                "inference_run_id": failed["run_id"],
                "metric_names": [
                    "failed_image_count",
                    "prediction_image_ratio",
                ],
            },
        )

    assert partial.is_error is False
    assert partial.structured_content["coverage"]["run_status"] == "partial"
    assert partial.structured_content["coverage"]["pending_image_count"] > 0
    assert failed_result.is_error is False
    assert failed_result.structured_content["coverage"]["run_status"] == "failed"
    failed_metrics = {
        item["metric_name"]: item
        for item in failed_result.structured_content["metrics"]
    }
    assert failed_metrics["failed_image_count"]["value"] > 0
    assert failed_metrics["prediction_image_ratio"]["value"] is None
    assert failed_metrics["prediction_image_ratio"]["evidence_status"] == "unavailable"


@pytest.mark.anyio
async def test_incompatible_captured_comparison_is_rejected(postgres_engine, tmp_path):
    first = build_inference_scope(postgres_engine, tmp_path, "compare-one")
    second = build_inference_scope(postgres_engine, tmp_path, "compare-two")
    first_run = run_scope(first, "cpu", prediction)
    second_run = run_scope(second, "cpu", prediction)
    snapshot = capture_context_snapshot(
        postgres_engine,
        [
            ("left", analytics_scope(first, first_run)),
            ("right", analytics_scope(second, second_run)),
        ],
        ["batch_image_count"],
    )
    server = create_mcp_server(
        postgres_engine,
        FixedEmbeddingBackend(),
        MCPSettings(token="mcp-integration-token-24-characters"),
    )

    async with Client(server) as client:
        result = await client.call_tool(
            "compare_batches",
            {
                "snapshot_id": snapshot["id"],
                "left_batch_id": first["batch"]["batch_id"],
                "left_inference_run_id": first_run,
                "right_batch_id": second["batch"]["batch_id"],
                "right_inference_run_id": second_run,
                "metric_names": ["batch_image_count"],
            },
        )

    assert result.is_error is True
    assert "incompatible captured comparison" in result.content[0].text


@pytest.mark.anyio
async def test_least_privilege_role_can_read_tools_but_not_write(
    postgres_engine, tmp_path
):
    fixture = build_inference_scope(postgres_engine, tmp_path, "readonly-mcp")
    run_id = run_scope(fixture, "cpu", lambda *args: [])
    snapshot = capture_context_snapshot(
        postgres_engine,
        [("primary", analytics_scope(fixture, run_id))],
        ["batch_image_count"],
    )
    password = "readonly-mcp-test-password"
    with postgres_engine.begin() as connection:
        connection.execute(
            text("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_roles WHERE rolname = 'visionq_mcp_test'
                    ) THEN
                        CREATE ROLE visionq_mcp_test LOGIN PASSWORD
                            'readonly-mcp-test-password';
                    END IF;
                END
                $$
            """)
        )
        connection.execute(
            text("ALTER ROLE visionq_mcp_test SET default_transaction_read_only = on")
        )
        connection.execute(
            text("GRANT CONNECT ON DATABASE visionq_t4_test TO visionq_mcp_test")
        )
        connection.execute(text("GRANT USAGE ON SCHEMA public TO visionq_mcp_test"))
        connection.execute(
            text("GRANT SELECT ON ALL TABLES IN SCHEMA public TO visionq_mcp_test")
        )
    readonly_engine = create_engine(
        "postgresql+psycopg://visionq_mcp_test:"
        f"{password}@{postgres_engine.url.host}:{postgres_engine.url.port}/"
        "visionq_t4_test",
        pool_pre_ping=True,
    )
    server = create_mcp_server(
        readonly_engine,
        FixedEmbeddingBackend(),
        MCPSettings(
            token="mcp-integration-token-24-characters",
            query_timeout_ms=2_000,
        ),
    )
    async with Client(server) as client:
        result = await client.call_tool(
            "get_batch_metrics",
            {
                "snapshot_id": snapshot["id"],
                "batch_id": fixture["batch"]["batch_id"],
                "inference_run_id": run_id,
                "metric_names": ["batch_image_count"],
            },
        )
    assert result.is_error is False
    with readonly_engine.begin() as connection:
        with pytest.raises(Exception, match="read-only"):
            connection.execute(
                text("""
                    INSERT INTO quality_issues (
                        id, dataset_version_id, rule_id, severity, details
                    ) VALUES (
                        gen_random_uuid(), CAST(:dataset AS uuid),
                        'readonly-forbidden', 'warning', '{}'::jsonb
                    )
                """),
                {"dataset": fixture["batch"]["dataset_version_id"]},
            )
    readonly_engine.dispose()
