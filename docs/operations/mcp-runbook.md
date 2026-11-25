# Read-only MCP runbook (M4.T3)

Scope: the local M4.T3 Streamable HTTP service. This runbook establishes the
server, five-tool contract and read-only PostgreSQL boundary. It does not verify
real EmbeddingGemma retrieval or live Azure operation.

## Evidence and transport

The server uses official MCP Python SDK 2.3.x and exposes exactly:

1. `get_batch_metrics`
2. `compare_batches`
3. `get_quality_report`
4. `get_run_provenance`
5. `search_documents`

The endpoint is `/mcp` over Streamable HTTP. Every request requires
`Authorization: Bearer <VISIONQ_MCP_TOKEN>`. Transport DNS-rebinding protection
allows loopback and the internal Compose hostname `mcp`; the Compose service
publishes no host port. Its default `tools` profile keeps it off the base stack.

The API, not MCP, creates analytics snapshots or evidence records. MCP reads an
immutable snapshot and never calculates replacement live metrics. The evidence-v2
snapshot authorizes its left/right/primary scopes, captures detailed quality
findings and pins one ready corpus/index pair. Historical M4.T1 single-run
snapshots remain readable for batch metrics and provenance, but cannot support
paired comparisons or pinned retrieval; the server returns an explicit
unsupported-evidence error.

## Least-privilege database role

Apply [mcp-readonly-role.sql](../../deploy/mcp-readonly-role.sql) with the
database owner/admin account and a secret supplied only through a psql variable:

```zsh
psql "$VISIONQ_ADMIN_DATABASE_URL" \
  -v visionq_mcp_password="$VISIONQ_MCP_PASSWORD" \
  -f deploy/mcp-readonly-role.sql
```

The role is `visionq_mcp`. It has only `CONNECT`, schema `USAGE` and `SELECT`
on application tables, plus default read-only transactions and a five-second
statement timeout. Do not put the role password in source control, shell history
or the SQL file. Re-run the grant after migrations add tables.

Configure:

```text
VISIONQ_MCP_DATABASE_URL=postgresql+psycopg://visionq_mcp:<secret>@db/visionq
VISIONQ_MCP_TOKEN=<separate bearer secret of at least 24 characters>
VISIONQ_MCP_EMBEDDING_BACKEND=deterministic
VISIONQ_MCP_EMBEDDING_DIMENSIONS=8
```

The deterministic backend is a fixture profile. For later live integration use
`openai-compatible` plus the explicit private vLLM base URL, model revision,
dimensions and prefixes. A different profile is rejected if it does not match
the snapshot's pinned index.

## Tool safeguards

- Snapshot IDs are verified for valid UUID, checksum and captured format.
- Metric names are allowlisted by the canonical M4.T1 catalogue.
- Batch/run/dataset/class scope IDs must exactly match captured authorization.
- Comparisons use `compare_payloads` on immutable captured values and reject
  changed datasets, checkpoints, preprocessing, thresholds, classes or
  definitions.
- `get_quality_report` reads captured findings, not live `quality_issues`.
- `search_documents` accepts only the exact pinned corpus/index pair and
  rejects top-k above four at schema validation.
- Database transactions are read-only, have statement timeouts and the whole
  caller receives a separate tool deadline. Eight synchronous operations can run per MCP process. A timed-out operation holds its slot until the underlying call returns. Saturation produces an explicit busy error.
- Retrieved text remains untrusted source data, never an instruction channel.
- No shell, filesystem, arbitrary URL or SQL execution tools are registered.

GET `/health` checks process liveness. GET `/ready` reads the snapshot schema through the configured database role. Live embedding availability is checked by a retrieval request.

## Checks

Run strict PostgreSQL/MCP tests through the project's isolated database
environment. The key client-server test starts an actual Uvicorn Streamable HTTP
service, authenticates with the official `mcp.Client`, discovers exactly five
tools, invokes every tool and verifies no analytics/retrieval row count changes.
Invalid metrics, classes, snapshot IDs, corpus pins and top-k values must return
MCP tool errors without creating rows. An unavailable database and timeout must
also return explicit errors.
