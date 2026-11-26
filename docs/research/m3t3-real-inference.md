# M3.T3 real inference — 26 November 2026

Status: supported inference acceptance passed; M3.T3 and M3 closure remain BLOCKED on requested PostgreSQL evaluation provenance persistence. Existing implementation has no evaluation-link persistence (src/analytics/service.py explicitly reports unavailable). No scope expansion or M4 implementation performed.

## Real results
252 exact frozen test members;252 succeeded,0 failed/pending/running;553 persisted detections;20 successful zero-detection images;252 overlays generated exclusively from persisted records. Predictions remain distinct from4182 ground-truth boxes; original catalog snapshot unchanged. Original evaluation remains authoritative, never rerun or replaced. Frozen model/settings unchanged; MPS nondeterminism remains.

Dataset version dc3b8671-354c-5393-930a-0e98cb0c04fd
Model 48c57c53-4b08-5a26-b429-ffe7bf3d2b43
Batch 11ca8c10-8639-5ec6-9bf0-f99c42fefd53
Run fe274f2d-4def-575b-8aa1-a46c04f61624
Analytics snapshot 49e902e7-9903-55bf-b5f2-1ee0301f0fb6
Catalog artifact root: artifacts/m2t4-real-9Sm1lP/catalog-artifacts
PostgreSQL: existing visionq-t4-real9sm-source-db-1, loopback current port50071, database visionq_t4_test. Credentials remain in existing private env file; its old port58083 is stale. No credentials included here.

Model row preserves checkpoint34754401c0f2becaa5c3ed12ce9d1d2c082471f77dd0ad167bde26d0e9db23d0, training0bbff140fb0697e431d76439087829f150207f0b540520968ee1f9954c120810 and selection cde036a43219271f1100f8faee800bde74d737f56ccf7d2a8dad336397bdbd69 plus exact inference configuration. Authoritative test216bcf12491b92ed94511894ccb68a6130b41c43c17d983ccb16e63218d7e77b and performance c9625f52019aa1ebac03ee77f33e901f5b887e9b133a5679b5ab6778254dea4a are verified external evidence, NOT registered evaluation records in PostgreSQL.

## Acceptance evidence
Controlled interruption after17 real committed images; partial state preserved, same-run resume completed252. Repeat registration identical; repeat inference with forbidden predictor made no new model calls. Reconciliation checks saved prediction artifacts against database boxes/confidences/coordinates and overlays; all passed. Prediction-snapshot.json captures persisted rows, model.json/batch.json/status.json preserve identities. Real final failures0; synthetic regression tests exercise explicit failure coverage rather than inventing real failures. Strict full regression328 passed, zero skips,72.54 seconds, including inference/recovery/schema/analytics/API/MCP/dashboard contracts. Post-regression reconciliation and frozen evaluation verification passed.

Two evidence-run errors preserved: initial stale database port caused connection refusal before writes; later snapshot exporter used nonexistent inference_items after inference completed. finish.py corrected only the export step; no repeated real inference. Existing source and restore containers restarted for this authorized task; retained running for availability, volumes preserved. No Azure actions, commit or push.

## M4 live integration handoff — not started
First resolve the PostgreSQL evaluation provenance gap through an explicitly scoped implementation task; do not close M3 merely because predictions pass. Persist verified evaluation/performance digests and immutable linkage to model, selection and dataset without storing research metrics as operational prediction counts. Add verification and regression coverage, then re-run affected M3 closure checks without rerunning held-out evaluation.

For live M4, configure existing API/MCP/dashboard processes to the SAME real catalog database and catalog artifact root above. The real data lives in the retained isolated acceptance catalog, not automatically in the default Compose database. If moving it, use a reviewed complete inference-aware transfer; the old M2 backup predates predictions. Do not assume the M2 catalog-only backup covers inference rows.

Use the exact batch/model/run/snapshot IDs above. Verify analytics counts252/553/20 and explicit zero failed coverage, API/MCP scoped read access and image/overlay path resolution. Check dashboard real batch selection, overlays and evidence provenance. Confirm evaluation links become available only after their persistence gap is resolved. Exercise live LLM/RAG integration under existing M4 gates separately; no Azure/model-service actions were taken here. Original M3.T2 figures and limitations remain authoritative.
