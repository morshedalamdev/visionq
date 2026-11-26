# M3 provenance correction and module closure — 26 November 2026

M3.T1, M3.T2, M3.T3 and M3 module gate PASSED. This record supersedes the earlier evaluation-link blocker. Owner authorized this bounded correction; no held-out evaluation, training, Azure action, commit or push was performed.

## Implementation
Migration0008_detector_evidence adds immutable model/dataset-scoped evaluation/performance records, original manifest bytes and full JSONB results, performance-to-evaluation FK, and one authoritative evaluation per model. Registered model relationships retain checkpoint, training, validation selection and operating configuration; verified export manifest binds frozen dataset membership. Application ingestion independently verifies all existing seals and model lineage, rehashes copied artifact bytes, rejects conflicts and repeats idempotently. CLI inference-register-evidence exposes the importer. No new dependencies.

New analytics evidence contains model-level research links separate from ground truth and operational metrics. Existing snapshots are not rewritten. Initial import preserved29 historical snapshots; repeat import after tests preserved44. New real snapshot efe6d71f-7b7a-53ad-98a8-67011c1e835b contains both links. Context snapshots inherit them for existing API/MCP provenance paths. Model-level scope is explicitly labeled even for class-filtered operational queries. Synthetic behavior is retained.

Schema details: docs/design/detector-evidence-schema.md.

## Registered authoritative identities
Dataset dc3b8671-354c-5393-930a-0e98cb0c04fd; model48c57c53-4b08-5a26-b429-ffe7bf3d2b43.
Evaluation216bcf12491b92ed94511894ccb68a6130b41c43c17d983ccb16e63218d7e77b.
Performance c9625f52019aa1ebac03ee77f33e901f5b887e9b133a5679b5ab6778254dea4a.
Checkpoint34754401c0f2becaa5c3ed12ce9d1d2c082471f77dd0ad167bde26d0e9db23d0.
Selection cde036a43219271f1100f8faee800bde74d737f56ccf7d2a8dad336397bdbd69.
Training0bbff140fb0697e431d76439087829f150207f0b540520968ee1f9954c120810.

PostgreSQL stores original manifest bytes; their SHA256 and decoded JSON were independently compared with persisted payloads. Stored metrics:252 images,574 truth boxes,381TP/172FP/193FN; P/R/F1 .688969/.663763/.676131; macro-F1 .653163; AP50 .728316,AP50–95 .434275. Per-class support/AP/P/R/F1, error categories and representative examples are retained. Benchmark retains hardware/environment and100 observations,10warmups,float32,MPS,batch1; full pipeline median13.396542ms,p9514.326750ms; inference median10.032104ms,p9510.796334ms. No inferred or fabricated values. MPS nondeterminism, weak crazing recall and original benchmark summary wording limitations remain in research records.

Operational run fe274f2d-4def-575b-8aa1-a46c04f61624 remains252 successful results,553 detections,20 successful zero-detection images,252 overlays,0 failures. Original reconciliation remains exactly equal; no predictions or annotations changed.

## Verification
Strict full suite331 passed,zero skips,70.89s. Prior full330-pass run and two test-only follow-up failures retained: duplicate module filename and fixed fixture hash collision. Both fixed; final full gate clean. Focused mismatch/immutability/scope tests and real repeated registration passed. Existing verifier tests cover corrupt sealed artifacts; new input test ensures failure before DB access. Static lint/format and diff checks passed. Restore database migration0008→0007→0008 passed and preserved historical analytics payloads/hashes; real source evidence was not downgraded. Evidence under artifacts/m3-provenance, sealed by evidence-manifest.json/.sha256.

## Exact M4 live handoff — not executed
Use dataset/model/run IDs above, batch11ca8c10-8639-5ec6-9bf0-f99c42fefd53, and new snapshot efe6d71f-7b7a-53ad-98a8-67011c1e835b. Historical snapshot49e902e7-9903-55bf-b5f2-1ee0301f0fb6 intentionally remains unchanged without new links.

1. Point VISIONQ_DATABASE_URL at the retained real local catalog (visionq-t4-real9sm-source-db-1,current loopback50071,database visionq_t4_test). Source the existing private env file and resolve the current published port; do not expose credentials. Apply migration head on any separate target before use.
2. Set ARTIFACT_ROOT=/Users/morshedalam/Developer/AI/visionq/artifacts/m2t4-real-9Sm1lP/catalog-artifacts. Configure VISIONQ_ANALYTICS_API_TOKEN per dashboard runbook. Frontend development VITE_API_TOKEN must match; production auth remains a separate live acceptance concern.
3. Configure VISIONQ_MCP_DATABASE_URL to the same database with the existing read-only role and VISIONQ_MCP_TOKEN. Reapply/verify deploy/mcp-readonly-role.sql grants for detector_evidence if needed. Verify scoped analytics and MCP provenance expose BOTH authoritative records, without treating them as batch/class-filtered predictions.
4. Run authenticated API/MCP/dashboard live checks: select real batch/run, reconcile252/553/20 counts, render persisted overlays, verify new snapshot evidence and original held-out metrics. Existing contract regressions passed; live browser/service verification remains M4 work.
5. Complete existing live LLM/RAG/corpus/authentication and M4 module gates. No new service or Azure work is implied by M3 closure. Any transfer/backup must include inference tables, detector_evidence, snapshots and referenced artifact bytes: old M2 catalog-only backup is insufficient for complete M3 recovery.
