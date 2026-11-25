# React dashboard and application runbook (M4.T4)

Scope: local M4.T4 application integration. The React frontend never connects
directly to PostgreSQL or MCP. It calls the authenticated FastAPI boundary.
Synthetic evidence remains explicitly labeled; Qwen, live EmbeddingGemma and
research claims are not implemented by this task.

## Backend

Migrate PostgreSQL to `0007_upload_requests`, configure:

```text
VISIONQ_DATABASE_URL=postgresql+psycopg://...
ARTIFACT_ROOT=/approved/local/artifact/root
VISIONQ_ANALYTICS_API_TOKEN=<private bearer token>
```

Start locally:

```zsh
uv run uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Compose supports the same boundary through `docker compose --profile tools up
api`; the host port is restricted to `127.0.0.1:8000`.

Dashboard endpoints are under `/app` and require the same bearer token as the
analytics API:

- `/app/datasets` and `/app/datasets/{id}`
- `/app/batches`
- `/app/runs`, `/app/runs/{id}` and `/app/runs/{id}/images`
- `/app/artifacts/{sha256}` for allowlisted catalog image artifacts
- `/app/uploads`, `/app/uploads/{id}` and `/app/uploads/{id}/image`
- `/app/agent-fixture`

Lists use bounded `limit`/`offset` pagination and stable ordering. Dataset,
batch, model, status and creation-date filters prevent accidental cross-run
mixing. Artifact delivery accepts only a 64-character registered image hash,
re-verifies stored bytes and converts supported stored images to PNG.

## Upload contract

The upload endpoint accepts only PNG/JPEG up to 20 MiB and 10 megapixels. It
sniffs decoded content, verifies dimensions and writes a content-addressed blob
under `<ARTIFACT_ROOT>/uploads/objects/<sha256>` before creating
`image_upload_requests`.

A valid request is `ready` for human/local review. `inference_state` is
`not_started` without a requested scope or `pending_registration` with an
explicit existing dataset/batch pair. No M4.T4 code registers the bytes as a
catalog dataset item, starts a worker, or fabricates detections. Identical bytes
are idempotent; the same checksum cannot silently switch dataset/batch scope.
Unsafe MIME/encoding, invalid scope, oversized pixels and checksum conflicts
return explicit failures.

## React

```zsh
cd src/web
npm install
cp .env.example .env.local
# Set VITE_API_TOKEN to a local development token matching the backend.
npm run dev
```

Vite binds to `127.0.0.1:5173` and proxies `/api` to FastAPI. The production
bundle is:

```zsh
npm test
npm run build
```

Screens:

- dataset quality and split/rule evidence;
- persistent batch/run history with filters;
- authenticated image rendering and original-coordinate overlays;
- canonical immutable analytics snapshots and paired comparisons;
- local upload validation/request history;
- explicitly labeled, non-live agent/evidence fixture.

Precision, recall and mAP stay unavailable until authoritative evaluation rows
exist. Prediction confidence and prediction/image ratios are never labeled as
accuracy. Retrieved/document and agent fixture materials are untrusted display
data.

## Restart and security checks

Restart FastAPI and reopen the UI; datasets, runs, snapshots and upload request
metadata remain in PostgreSQL and content-addressed artifacts remain under the
artifact root. Requests without a bearer token fail. Path traversal, unknown
artifact hashes, unsupported files, invalid dates/UUIDs, oversized uploads and
incompatible analytics scopes return explicit client errors. Public hosting
topology remains unapproved and is not configured here.


GET `/health` checks process liveness. GET `/ready` checks that an API token is
configured, the artifact root is accessible and the upload table can be read.
The API can start with document search disabled. For live search, set
`VISIONQ_API_EMBEDDING_BACKEND=openai-compatible` and supply the same private
vLLM model, revision, dimensions and prefixes used to build the index.
