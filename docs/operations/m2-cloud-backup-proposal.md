# M2 cloud backup proposal — 26 November 2026

Owner approved the exact scope and hybrid criteria; actual acceptance passed on 26 November 2026. See [hybrid recovery evidence](m2-hybrid-recovery-acceptance.md). This proposal is retained as historical scope evidence; no additional bytes were authorized or uploaded.

Status: **proposal only; no Azure access or upload authorized/executed**.
M2 remains blocked. No accepted plan/architecture requirement has been amended.

The verified local full backup contains 7180 files /117644072 bytes. Its7175
content-addressed objects comprise:

| Classification | Objects | Bytes |
|---|---:|---:|
| Original images |1799|26771251|
| Generated images |1797|64530378|
| Annotations/reviews/lineage-bearing release evidence |3574|8301471|
| Catalog metadata |4|1119588|
| Source metadata (.DS_Store) |1|6148|

Five backup-envelope files add16915236 bytes. catalog.json (7692580 bytes) and
specification.json (8087463 bytes) include all4182 box records and1797 annotation
lineage records; they are not unrestricted cloud metadata. The four metadata
objects are the extracted-source manifest, export manifest, importer configuration
and data.yaml; automatic cloud eligibility does not follow from the category name.
The1799 original-image objects represent1800 source files, with identical bytes
stored once. No model weights are present in this backup.

Existing rights.json permits only owner-authorized private local backup/restore;
cloud_upload=false for every category. Source inventory still records unknown
acquisition details, unavailable original archive identity and unresolved explicit
redistribution terms. No new terms or rights-holder permission were inferred.
Private Blob access controls do not establish source copying rights. Full cloud
backup requires documented permission for private third-party cloud copying of
original and derived data plus the owner's exact operational authorization.

## Proposed scope, not a complete dataset backup

Fresh proposal: `artifacts/m2-cloud-scope-Jbfvpr/proposed-cloud/`.
Six files /3615 bytes: recovery-anchor.json, exclusions.json, scope.json,
RECOVERY.txt, inclusion-manifest.json and COMPLETE. Only aggregate catalog/split
counts, opaque checksums, scope and recovery instructions. No images, XML, labels,
boxes, per-image membership/path mappings, reviewer text, credentials or weights.

Inclusion-manifest SHA-256:
`9b85738ad6893f44c4cb642529357427863f847f7628d236c53870e2b08dedd9`.

`assessment.json` gives measured counts/sizes. `local-only-exclusion-detail.json`
lists every excluded existing backup file and checksum; it is NOT in the cloud
proposal. The control exclusions.json summarizes exclusions and pins that local
list. Original backup manifest remains
`84d2abb102ac3d94bd9f7f2f07f4ef588089383c2ab4446193387ab4051a0609`.

## Proposed hybrid acceptance amendment

Cloud contains only the approved recovery anchor/control metadata. An independent
owner-controlled offline medium retains the full local catalog/artifact backup.
Cloud loss or offline-backup loss must be addressed by retention policy; cloud
alone cannot recover the dataset. A second directory on the same Mac does not
establish independent retention.

Proposed acceptance: exact private upload/download and hash verification of the
approved scope, anonymous-access denial, then fresh PostgreSQL restoration of the
independently retained full backup verified against the downloaded anchor. All
catalog rows, frozen membership and7175 artifact hashes must match; reconciliation
must be clean. Missing/corrupt control or local backup must fail closed. Preserve
local versus cloud evidence and the residual dependency explicitly.

This is a proposed REPLACEMENT for the complete cloud-catalog requirement, not
proof that the unchanged requirement passed. Owner must approve the revised
criteria before the development plan/architecture are amended. Alternatively,
obtain suitable rights evidence and approve complete private cloud backup.

## Exact future execution

`artifacts/m2-cloud-scope-Jbfvpr/AFTER-APPROVAL.md` contains complete Mac/zsh upload,
read-back verification, create-only download, anonymous-denial, independently
retained full-backup verification, fresh local restore and reconciliation commands.
`transport.py` reuses existing `worker.backup.Azure`/Directory adapters with a
separate versioned control prefix, private-container check, pinned manifest,
create-only/resumable matching writes and COMPLETE-last semantics. It does not
change or bypass the real catalog's local-only backup guard or foundation format.

Only local integrity and altered-member rejection were exercised; Azure execution
and the hybrid restore remain NOT RUN. Successful prior regression/restore suites
were not repeated. VM state was not changed; no Azure call was made.

Required owner decisions: exact six-file digest/scope; hybrid acceptance amendment;
existing private account/container; independent backup location and retention
responsibility. No credentials or tokens are requested. Keep M2 open until the
approved path has actual passing cloud/recovery evidence. M3 training remains gated.
