# Batch inference runbook (M3.T3)

Scope: development use with the isolated synthetic dataset and verified synthetic
checkpoint. Real NEU-DET batch inference remains blocked until the M2 release and
real M3 gates are accepted.

## Data flow

1. `inference-register-batch` records an immutable exact asset membership.
2. `inference-register-model` verifies a sealed M3.T2 selection, checks its
   checkpoint SHA-256 and dataset release identity, then registers the checkpoint
   as a content-addressed catalog artifact.
3. `inference-run` creates a deterministic run from batch, model and canonical
   configuration. A failed or interrupted invocation resumes that same run.
4. Each image result and all of its detections commit in one PostgreSQL
   transaction. A successful zero-detection result has `detection_count = 0`
   and no rows in `detections`.
5. `inference-overlays` reads `detections` from PostgreSQL. It never runs the
   detector and never modifies source-image bytes.
6. `inference-reconcile` reports membership, checksum, status, count and artifact
   findings. It is read-only and performs no repair.

## Commands

Supply `VISIONQ_DATABASE_URL` explicitly for the disposable loopback database.

```zsh
uv run --locked python -m worker inference-register-batch \
  --dataset-version-id UUID \
  --split test \
  --artifact-root ROOT

uv run --locked python -m worker inference-register-model \
  --dataset-version-id UUID \
  --selection artifacts/m3t2-select-recheck-20261121-135925 \
  --selection-sha SHA256 \
  --artifact-root ROOT

uv run --locked python -m worker inference-run \
  --batch-id UUID \
  --model-id UUID \
  --artifact-root ROOT \
  --device mps

uv run --locked python -m worker inference-status --run-id UUID

uv run --locked python -m worker inference-overlays \
  --run-id UUID \
  --artifact-root ROOT

uv run --locked python -m worker inference-reconcile \
  --run-id UUID \
  --artifact-root ROOT
```

To resume, rerun `inference-run` with the same inputs and the returned run UUID:

```zsh
uv run --locked python -m worker inference-run \
  --batch-id UUID \
  --model-id UUID \
  --artifact-root ROOT \
  --device mps \
  --resume-run UUID
```

The resume command is rejected if the run identity differs. A successful image
is not inferenced again. Each failed image can be attempted at most three times;
exhaustion remains an explicit failure for review.

## Reconciliation and failure handling

| Finding | Meaning | Required action |
|---|---|---|
| `incomplete_run` / `incomplete_item` | Run or image is pending/failed | Resume with identical inputs |
| `corrupt_checkpoint` / `corrupt_image` / `corrupt_overlay` | Content no longer matches its stored SHA-256 | Restore the exact verified artifact |
| `batch_membership_checksum` | Registered batch members changed | Treat as corruption; do not repair in place |
| `detection_count` / `prediction_count` | Persisted row counts are inconsistent | Stop and investigate transaction/schema integrity |

Reconciliation exits nonzero on any finding and never deletes, rewrites or
regenerates records silently. Overlay generation is idempotent and preserves
the original image artifact.

## Focused verification

```zsh
uv run --locked alembic upgrade head
uv run --locked alembic current
uv run --locked ruff check migrations src tests
uv run --locked ruff format --check migrations src tests

export VISIONQ_T4_SCHEMA_TEST=1
export VISIONQ_REQUIRE_T4_TESTS=1
uv run --locked python -m pytest \
  tests/unit/test_inference.py \
  tests/unit/test_detection_overlay.py \
  tests/unit/test_cli.py \
  tests/integration/test_inference_schema.py \
  tests/integration/test_inference_pipeline.py \
  -q -rs
```

PostgreSQL skips are not passes. For the strict focused command above, any skip
fails.
