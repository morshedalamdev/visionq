# M2.T4 real ingestion kickoff — frozen NEU-DET v1

Update 26 November 2026: the local implementation and execution below are complete;
see [actual evidence](../research/dataset-v1-catalog.md). The synthetic-only guard
was extended narrowly for pinned NEU-DET v1, not removed globally. The original
kickoff below is retained as history. Mandatory cloud backup gate remains open.

M2.T3 is passed; its private local release is accepted. Continue existing T4,
without creating a second catalog or regenerating membership. No database service,
migration, import or cloud operation was executed by this handoff.

## Pinned package

Repository: `/Users/morshedalam/Developer/AI/visionq`.

- Source: `dataset/NEU-DET`.
- Baseline: `artifacts/m2t1-dV4jxu/run3/manifest.json`.
- T2 packet: `artifacts/m2t2-repair-pBMtK3/one-review`.
- Component packet: `artifacts/m2t3-final-isolation-BCvxnD/packet-a`.
- Constraint: `artifacts/m2t3-final-isolation-BCvxnD/approved-isolation.json`.
- Release: `artifacts/m2t3-release-v1-eNmh2g/export-a`.
- Manifest SHA-256: `a8c14d88958f29a3042ba8b925584a9d6c770f60979cedb8bf9817ed393dc3c6`.
- Frozen membership: `artifacts/m2t3-release-v1-eNmh2g/frozen-membership.json`.
- Acceptance/receipts: `artifacts/m2t3-release-v1-eNmh2g/`.
- Intended catalog name/version: `NEU-DET`, `1`; confirm database namespace is
  unused or exactly matches before first import. Never use a synthetic prefix
  to circumvent authorization.

All pins are listed in [dataset-v1-release](../research/dataset-v1-release.md).

## First implementation checkpoint

Inspect current `catalog_input.load_package`, catalog CLI, ingestion,
reconciliation/backup adapters and their existing real-PostgreSQL tests. The
current importer intentionally rejects non-`synthetic-` names. It also reconstructs
only the default pair-review plan and rejects near candidates. Therefore the
existing catalog-import command is NOT yet usable for this real release.

Extend that existing input contract with a fail-closed real-release authorization
path that verifies the exact manifest, frozen membership, genuine T2/component
receipts, pinned constraint and all associated source/annotation identities.
Reconstruct the approved component policy with the approved constraint; do not
remove the guard globally or silently accept arbitrary real releases. Preserve
synthetic behavior and inspection_fixture. Ensure backup/restore revalidation
consumes the same bound authorization evidence. Add focused rejection tests for
missing/stale approvals and source/manifest/membership/constraint tampering.

## Real acceptance execution after that checkpoint

Use the established dedicated local PostgreSQL configuration and fresh evidence
and artifact destinations. Preserve existing records. Do not blindly reset the
application database. Execute existing catalog CLI with the pinned package:

1. Import NEU-DET version 1; verify counts, all annotation/source lineage, split
   membership, persisted operation success and artifact checksums.
2. Repeat identical import; logical counts and identities must be unchanged.
3. Prove interruption/resume safely using isolated fixtures or an explicitly
   isolated operation, retaining existing valid transaction tests; no raw edits.
4. Run deterministic read-only reconciliation; compare repeated reports and
   require no missing/unexpected/conflicting/corrupt records or artifacts.
5. Review backup eligibility separately for metadata, annotations, generated
   images and original data. Perform authorized local backup and fresh isolated
   restore; verify every required object and post-restore reconciliation.
6. Reuse valid synthetic/CI evidence; run affected focused PostgreSQL/regression
   checks and record exact commands, exit codes, counts and hashes.

Real private Blob backup/restore remains separately rights- and authorization-
gated under the development plan. No Azure access, uploads or paid resources are
authorized here. Metadata-only backups cannot establish complete artifact recovery.
Keep M2.T4 and M2 open until all actual gates, including this separate backup
boundary, are resolved. No detector training or test-driven split changes.
