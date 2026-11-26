# NEU-DET dataset v1 — accepted 25 November 2026

M2 module closed on 26 November 2026 after [owner-approved hybrid recovery](../operations/m2-hybrid-recovery-acceptance.md) passed. Dataset identities and frozen membership below are unchanged.

M2.T3 status: **passed** for the private local dataset release. M2 remains open
for rights-reviewed cloud backup acceptance in M2.T4. Real local ingestion and
recovery passed on 26 November; see [catalog evidence](dataset-v1-catalog.md).
No training, Azure operation, commit or push was performed during release.

## Immutable identities and locations

Repository baseline: `9e647f4e688664ca0c94764e4894e3fa10d7b8ed`.
Evidence root: `artifacts/m2t3-release-v1-eNmh2g/`.
Primary export: `artifacts/m2t3-release-v1-eNmh2g/export-a/`.
Independent matching export: `artifacts/m2t3-release-v1-eNmh2g/export-b/`.

| Identity | SHA-256 |
|---|---|
| Both export manifests | `a8c14d88958f29a3042ba8b925584a9d6c770f60979cedb8bf9817ed393dc3c6` |
| Frozen membership | `508066a66900129626f2d9c6291dd7565ddfb278d53cf23f0b67faa8f6b8b41b` |
| Approved plan | `0585278c54569a17c98142fa80250bf649c872ce5f2405a8942486b27f369b69` |
| Component packet | `c324d4df23a9f4c879c7aa4b097ec64ee959b6acbc4e954c3043da94038732c3` |
| Genuine component review | `7193ec48d567394ccca0ea2b225d0ea96206dd435fc34396bd0bb6f1a88d83e8` |
| Component manifest | `67f6ff6e6c56e0556229b87e5209178176f701d9e56484b49efb79fbd6e9e1b8` |
| Approved isolation constraint | `4af6862a012ba3a89f7626934f7cf669739d99122ed5b9e73eaf5a2d2d6079c9` |
| Original extracted-source manifest | `12d88cd4c70f984653ba6927729c0f584b29052895d0b0f32706b541dc6a1587` |

The last hash identifies the extracted copy, not the unavailable original archive.
The owner review was validated from files: Morshed, 24 components, timestamp
`2026-11-25T18:26:21.952550+08:00`. Owner explicitly authorized final release after
mandatory checks. The approved plan was not modified or reallocated. Export
recomputed it only to check equality.

## Membership and representation

1287 train / 258 validation / 252 test; 1797 unique eligible assets and 1661
allocation groups. Excluded: patches_101.jpg, patches_105.jpg, scratches_103.jpg.
All six classes occur in every split. Full class/box statistics remain in the
approved plan, release.json and preflight reports. Exact identity groups are
retained separately from conservative isolation groups. No source aliases or
annotation lineage were lost.

`frozen-membership.json` preserves ordered membership, identities, class map and
policy. Each export's `release.json` includes the exact approved plan, T2 and
component review receipts, constraint evidence and preprocessing contract.
`data.yaml` records the six canonical class IDs and relative split paths.
Native-size lossless PNG uses three identical grayscale-derived RGB channels;
normalized YOLO xywh labels preserve canonical half-open boxes. Loader owns
letterboxing; reference transforms remain in the preparation specification.
Training augmentation is train-only. No preprocessing is fitted on test data.

## Actual acceptance checks

`release-checks.py` records the exact execution and assertions. All invoked
review/export/preflight commands exited 0. No application code changed.

- DQ01–DQ06: original T2 audit reproduced exactly from source, reference and
  revision history. Every eligible input has no error-level finding; all boxes
  remain valid and annotation identities agree. Documented RGB/depth and
  extensionless-filename warnings remain covered by genuine T2 review.
- DQ07: conflicting patches_101/105 exact pair remains quarantined. Byte/pixel
  identities and aliases accounted for; human scratch exclusion preserved.
- DQ08: zero crossing allocation, exact, file-hash, decoded-pixel or source-lineage
  groups; zero crossing original 1083 candidate edges or approved added constraint.
  Unknown acquisition relationships cannot be certified absent.
- DQ09: all 3601 source files / 28208067 bytes match T1 before/after; both export
  manifests, exact file membership, sizes and hashes verified. Every exported RGB
  channel equals the source's grayscale pixels. Both complete exports are byte
  identical. Preflight validates every exported image and YOLO label.
- DQ10: full-source annotation-class counts reproduce the approved T2 reference.
  Every split retains all classes. Brightness compared against observed raw T2
  mean 128.28469: train 128.02744, validation 129.29934, test 129.00164; all deltas
  within the existing tolerance 20. No independent published brightness baseline
  exists. Count differences reflect partitioning and documented quarantine.

Evidence includes `acceptance.json`, `dq01-dq10-acceptance.json`,
`dq10-reference-comparison.json`, both preflight reports, both export-integrity
reports, source/protected snapshots, frozen membership, and command logs/exits.
Previously passed focused software regressions are retained; unrelated suites
were not repeated. Old review records and decisions remain unchanged.

## Limits and next task

Private local release does not resolve acquisition URL/date, original archive
identity or redistribution rights. No cloud/public upload authorized. Adopted
one-based-inclusive annotation interpretation remains; original endpoint semantics
are unverified. No verified official partitions exist for this copy. Project
splits are not a paper's official split. Similarity isolation cannot guarantee
all acquisition relationships were detected. No model-performance claim follows.

M2.T4 handoff: use these exact frozen inputs; see
[real ingestion kickoff](../operations/m2t4-real-ingestion-kickoff.md).
