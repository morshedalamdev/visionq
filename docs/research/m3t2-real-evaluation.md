# M3.T2 real detector evaluation — 26 November 2026

Status: passed. Owner declined corrective training and authorized validation selection then one held-out evaluation. No retraining, threshold tuning after test, Azure changes, commit/push or M3.T3 execution.

Frozen best.pt SHA256 34754401c0f2becaa5c3ed12ce9d1d2c082471f77dd0ad167bde26d0e9db23d0; confidence0.31, image320, NMS IoU0.7, max_det300, AP floor0.001, operating matching IoU0.5. Validation-only checkpoint/threshold selection verified before test execution. Full selection settings: artifacts/m3t2-real-selection/selection.json.

252/252 images evaluated,574 ground-truth boxes,381 TP,172 FP,193 FN. Operating micro P/R/F1=.688969/.663763/.676131; macro-F1=.653163. AP50=.728316, AP50–95=.434275. AP uses Ultralytics matching/rect batching; operating metrics use VisionQ matching and predict letterboxing. These are distinct protocols.

|Class|Support|Precision|Recall|F1|AP50|AP50–95|
|---|---:|---:|---:|---:|---:|---:|
|crazing|92|0.4857|0.1848|0.2677|0.3857|0.1612|
|inclusion|147|0.6645|0.7007|0.6821|0.7154|0.3827|
|patches|111|0.7939|0.9369|0.8595|0.9447|0.6417|
|pitted_surface|56|0.8696|0.7143|0.7843|0.7848|0.5425|
|rolled_in_scale|97|0.6471|0.5670|0.6044|0.6838|0.3478|
|scratches|71|0.6139|0.8732|0.7209|0.8554|0.5298|

## Latency

M4 16GiB MPS float32, batch1,10 warmups,100 timed observations on100 distinct images from252 eligible test assets; zero failures. Decode and synchronized preprocess/inference/postprocess measured separately; sequential throughput76.06 images/s. Benchmark uses frozen prediction floor0.001, not an optimized production pipeline.

|Stage|Median ms|p95 ms|
|---|---:|---:|
|decode|0.508|0.593|
|full_pipeline|13.397|14.327|
|inference|10.032|10.796|
|postprocess|1.899|2.184|
|preprocess|0.848|1.367|

## Failure analysis and limits

Crazing misses75/92 boxes; weak recall remains a research limitation. FP categories:76 localization,65 false alarms,30 duplicate boxes,1 class confusion;193 missed boxes overall. Deterministic representative boxes (up to3/category) and their source IDs are in test-evaluation.json;13 annotated crops in artifacts/m3t2-real-evidence. These categories are geometric diagnostics, not causal explanations. No healthy-image false-positive rate or industrial readiness can be inferred. MPS nondeterminism and unproven acquisition independence remain.

Supplemental confusion-matrix.json is derived from saved predictions, preserving official same-class matches then pairing remaining cross-class boxes at IoU>=.5; rows truth, columns prediction, background captures unmatched boxes, no true negatives. Its support/TP/prediction totals were asserted. derive.py records the exact method; no new model inference.

Benchmark summary.md has a stale synthetic-only closing sentence; authoritative JSON evidence_class is real-test. Its unique_image_count252 is the available pool, not timed unique images (100). Sealed outputs remain unmodified; this report corrects the interpretation.

## Acceptance and identities

58 focused evaluation/selection/test/performance tests passed. Selection520 artifacts, test509 artifacts and performance2 artifacts verified; both original training checkpoints verified/reloaded by selection input checks. Frozen export identity verified. All252 images covered with no failed images. Supplemental confusion accounting passed. M3.T2 passed; module remains open pending M3.T3 and integration gate.

Selection: artifacts/m3t2-real-selection; SHA256 `cde036a43219271f1100f8faee800bde74d737f56ccf7d2a8dad336397bdbd69`.

Test: artifacts/m3t2-real-test; SHA256 `216bcf12491b92ed94511894ccb68a6130b41c43c17d983ccb16e63218d7e77b`.

Performance: artifacts/m3t2-real-performance; SHA256 `c9625f52019aa1ebac03ee77f33e901f5b887e9b133a5679b5ab6778254dea4a`.

## Exact M3.T3 handoff — not executed

Use the existing real NEU-DET/version1 catalog and its existing artifact root; recover their exact dataset_version_id/root from the M2 catalog receipt, verify database identity before writes, and retain its existing backup. Do not substitute a synthetic catalog. Read src/worker/inference.py, CLI inference commands and existing inference tests before execution.

1. Register frozen model: `uv run --locked --group train visionq inference-register-model --dataset-version-id REAL_VERSION_UUID --selection artifacts/m3t2-real-selection --selection-sha cde036a43219271f1100f8faee800bde74d737f56ccf7d2a8dad336397bdbd69 --artifact-root EXISTING_ROOT --real-release-approved`.
2. Register exact252-image test membership using `inference-register-batch --dataset-version-id REAL_VERSION_UUID --split test --artifact-root EXISTING_ROOT --real-release-approved`. This is persistence/operational inference, not a fresh research evaluation or tuning opportunity.
3. Use returned IDs with `inference-run --batch-id BATCH_ID --model-id MODEL_ID --artifact-root EXISTING_ROOT --device mps`. Record run ID; inspect `inference-status --run-id RUN_ID` and exercise controlled failure/resume with `--resume-run RUN_ID` under existing tests/protocol.
4. Generate overlays with `inference-overlays --run-id RUN_ID --artifact-root EXISTING_ROOT`. Reconcile every persisted prediction/box with immutable run exports, including zero-detection successes and failures. Verify retry/restart creates no duplicates, immutable model/config/batch lineage, and original catalog preservation.
5. Execute required inference integration/regression checks with the existing isolated database setup, record actual evidence, then run the M3 module gate. Do not claim closure until all required checks pass. UUID/root placeholders are intentionally unresolved until the catalog is inspected; no database was started or modified in M3.T2.
