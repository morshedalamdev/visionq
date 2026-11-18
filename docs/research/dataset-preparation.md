# Dataset preparation implementation — 18 November 2026

Status: implemented and fixture-tested; real dataset release pending T2 human
review and near-duplicate review. The owner explicitly authorized T3 development
while T2 review remains open. This is not a waiver of either release gate.

## Components and integration

`src/worker/preparation.py` defines ordered components: policy and reference
letterbox transforms; transitive exact-byte/pixel grouping; deterministic
source-category allocation; perceptual candidate reporting; provisional plan
construction; review-gated export; and export integrity verification.
`src/worker/cli.py` exposes `prepare-dataset` and `export-dataset`.
`tests/unit/test_preparation.py` exercises those contracts with self-created data.
No new dependency, database table, migration or service is introduced.

Inputs are the preserved source root and a T2 packet (audit, selection, review).
Preparation verifies the original manifest, audit digest, image/XML identities
and decoded pixel hashes. It reads XML folder as source category, not object
class, and retains all annotation revision identities. Missing categories fail
closed. Whole exact-content groups are quarantined if any alias is excluded.
Unquarantined duplicate annotation conflicts fail rather than choosing a label.
One canonical asset is exported per exact group; all source aliases remain in
lineage. Acquisition groups are unknown and are not invented.

The fallback split uses seed 42, source-category strata, stable SHA-256 ordering
and weighted group allocation toward 70/15/15. Multi-label boxes remain intact.
All six box classes must be represented in every split before export. Tiny or
constrained strata may fail this gate; no test-driven seed search is allowed.

Optional `--official` JSON contains `verified_by`, `evidence`, and `membership`
mapping every source image to train/test. It must be independently verified;
the program validates membership consistency, not historical authenticity.
Official test membership is preserved, with validation derived from training.
Exact groups crossing official partitions block preparation. Quarantined official
members remain excluded and reported. Unrecognized auxiliary files block fallback
splitting until supplied partition metadata is reviewed. No official membership
has been verified for this local copy.

## Review and release boundary

`prepare-dataset` writes only a provisional plan, never training inputs.
`export-dataset` reruns the existing T2 review validator and recomputes the plan;
it checks an externally supplied plan SHA-256 and source identities. Changed
review records require a regenerated plan. Neither a successful CLI exit from
preparation nor fixture approvals authorize a real release.

Near candidates use 64-bit dHash at Hamming distance <=2. This simple heuristic
can overflag industrial textures and can miss other similarities. Candidates
are never silently merged. A near-review JSON must bind `plan_sha256`, identify
`reviewer`, and include exactly one item per candidate with its `groups` pair,
`decision: distinct`, and a nonempty observed `reason`. Each exception must be
reviewed. Related or unresolved candidates block export; confirmed additional
group relationships require a reviewed grouping amendment before release.
There is no claim that acquisition independence has been established.

## Preprocessing and M3 contract

Export preserves native dimensions and writes lossless PNG, converting through
L to RGB so all three channels are identical. Raw files are never edited.
Canonical zero-based half-open boxes become normalized YOLO xywh labels with
17 significant digits. No export resizing, denoising, contrast enhancement or
augmentation is performed. The model loader owns resizing/letterboxing and
normalization. Initial intended image size is 320; M3 must record its actual
library version, rounding, auto-padding, scale and padding. The tested square
letterbox helper is a reference non-auto transform, not proof of parity with
an uninstalled model library. Training augmentation applies only to train.

`data.yaml` contains relative train/val/test image paths and the six class IDs.
The M3 adapter must set `path` to the resolved export root when loading this
configuration. It must not rely on a process working directory or global dataset
location. Release bytes intentionally contain no machine-specific absolute path.
`release.json` retains the full plan, review receipt and loader contract.
`manifest.json` hashes all image/label/config/release bytes; `manifest.sha256`
is its digest. Verify that digest against an independently retained value with
`worker.preparation.verify_export`. Outputs are create-only.

## Observed evidence

Evidence root: `artifacts/m2t3-development/`.
Starting inspected revision: `eeda3d6dfd6bb8fe8ede3db822b7ab2d60da853d` with a
pre-existing validation-test working change, preserved. Final tested source and
lock hashes are in `code-hashes.json`. No commit or staging was performed.

- T2: 6 accepted / 23 pending in one-review; existing validator rejects the
  pending inclusion_10 item. One-based-inclusive remains the working candidate;
  source endpoint semantics remain unverified. No genuine passing receipt exists.
- Exact groups: 1,799 across 1,800 source images. The conflicting patches_101 /
  patches_105 group remains excluded (2 paths). Provisional eligible assets: 1,798.
- Provisional split: 1,258 train / 270 validation / 270 test; all six box classes
  present in each split. This is not final frozen test membership.
- Near-duplicate candidates: 1,136 pairs, awaiting documented review. No
  acquisition metadata or grouping conclusion has been fabricated.
- `plan/plan.json` and `repeat/plan.json` are byte-identical across both CLI entry
  points. These are not released training artifacts.
- `final-focused.log`: 10 passed. `final-tests.log`: 62 passed.
  `final-lint.log`: clean. `final-format.log`: 17 files formatted. CLI info passes.
- Synthetic-only exports: `synthetic-only/export-a/` and `export-b/`, 24 assets,
  50 manifest members, identical manifest digest
  `3ec61196f181354e3a01e57fef44f17446f5c7d555f4cf2fe070078859898125`.
  These establish software behavior, not annotation correctness or model results.
- `release-block.log`: real export rejected pending human review, exit 1 as
  required; no real output directory created.
- `preservation.json`: all 3,601 files / 28,208,067 bytes match T1 baseline digest
  `12d88cd4c70f984653ba6927729c0f584b29052895d0b0f32706b541dc6a1587`.
  All 347 captured prior evidence files remain unchanged. Raw/generated data are
  ignored and absent from tracked Git files.

Remaining: complete real T2 review and receipt, review near candidates, document
any grouping amendment, regenerate/verify the plan, release reproducibly and
freeze test membership before tuning. M2.T3 is not passed and M2.T4 is not ready.
