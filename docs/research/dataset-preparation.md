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

## Owner-approved conservative isolation — 25 November 2026

This section supersedes the historical pending-T2 and mandatory-pair-decision
statements above for the explicitly selected component policy. The original
pair-review policy remains the default and is backward compatible.

The owner approved `conservative_similarity_component`, algorithm
`dhash-connected-components-v1`, on 25 November 2026 in the M2 chat. The algorithm
uses every existing distance <=2 64-bit dHash candidate edge, without changing
threshold or seed 42. Vertices are eligible exact-byte/pixel groups. Deterministic
connected components become allocation groups before the existing weighted,
source-category-stratified allocation. A nontrivial component ID is SHA-256 of
canonical JSON containing sorted exact-group IDs; singleton IDs stay unchanged.
Each record retains `exact_group_id`, all source aliases, original asset and
annotation identities; `group_id` now identifies its allocation group. Similarity
components do not merge distinct assets or assert duplicates or shared acquisition.
Verified official train/test constraints take precedence: any component crossing
those boundaries fails preparation. None are verified for this source copy.

This is conservative isolation, not proof of acquisition independence. Transitive
chains can overgroup unrelated textures, producing large groups and less balanced
splits. The heuristic can miss similarities. No threshold/seed tuning or held-out
performance informed allocation. One-based-inclusive remains the adopted XML
interpretation; original endpoint semantics remain unverified. Acquisition,
original archive identity and redistribution terms remain unresolved.

### Commands and approval boundary

- `prepare-dataset --grouping-policy conservative_similarity_component` creates
  only a provisional plan. Existing `--root`, `--packet`, `--output`, and optional
  `--official` arguments retain their meanings.
- `component-review-packet --root ROOT --packet T2_PACKET --plan PLAN --plan-sha
  PLAN_SHA --output NEW_DIRECTORY` recomputes the plan, verifies T2 review and
  source identities, then writes contact sheets, individual boxed overlays,
  `index.html`, immutable `packet.json`, and editable `component-review.json`.
- `check-component-review --packet PACKET --packet-sha PINNED_SHA` validates static
  evidence and actual completed review. Save the digest outside the editable
  packet. Hashes bind bytes; they are not digital signatures or proof that someone
  visually reviewed the images.
- Future `export-dataset` use with this policy requires `--component-packet` and
  `--component-packet-sha`. It recomputes the plan, rechecks T2, validates the
  completed component review, and embeds its receipt. Missing/stale/modified or
  incomplete evidence blocks export. The original `--near-review` path remains
  available for original-policy plans.

Review every image in each component sheet, opening the linked enlarged overlay
when needed. Record `accept_isolation` only when the conservative grouping is
acceptable and no unresolved source/annotation issue requires action; write a
specific observed note. Otherwise record `unresolved` and the affected paths and
reason. This does not declare pairs distinct or duplicates. Enter the actual
reviewer and timezone-qualified completion timestamp, and confirm
`methodology_approved: true` for the bound methodology/plan. Leave IDs/digests
unchanged. All components must have genuine completed decisions. Findings needing
annotation changes or additional quarantine require a separate evidence-backed
amendment and regenerated plan/review; never edit raw data to resolve them.

### Verified provisional result (not a frozen release)

Evidence: `artifacts/m2t3-components-mHGL5B/`, baseline `42a2111`.
Both CLI entry points produced byte-identical plans and packets.

- 1,797 eligible images allocated exactly once: train 1,287; validation 258;
  test 252. All six annotation classes are represented in every split.
- Three preserved exclusions: patches_101.jpg, patches_105.jpg, scratches_103.jpg.
- 1,662 allocation groups; 25 nontrivial components covering 160 images. Largest
  component: 73 images. All 1,083 candidate edges remain within splits.
- Original asset/annotation lineage and all historical candidate records are
  unchanged. All 3,601 raw files / 28,208,067 bytes match the original T1 manifest.
- Plan SHA-256: `87e98bff05054ad5038dd2310be6b7eeabae75697aeb1e42340a71fe72a8b631`.
- Review packet SHA-256: `932f02c1c7a559cf353a16da3d3f1b29221caf188854380bc1501ace8a6c3415`.
- 71 focused preparation, validation/review, inventory, CLI and catalog-input
  compatibility tests passed. Locked dependency check, Ruff lint/format, CLI info
  and diff check passed. No M1 runtime checks were repeated.
- `focused.log` preserves an initial test-command error (nonexistent
  `tests/unit/test_review.py`); `focused-corrected.log` is the passing run.
- Pending-review validator exits 1 as required. No human component decision,
  passing real review receipt, frozen membership or final training export exists.

The original 1,083 pending pair decisions remain historical evidence. The next
release gate is genuine review of all 25 components, followed by a passing bound
receipt, final DQ08/membership freeze, reproducible export and export verification.

## Approved additional isolation constraint — 25 November 2026

The owner approved co-location of former components 17 and 18, retaining seven
separate images, their annotations and source identities. Translation-aware
original-pixel investigation found strong overlapping visual content; this does
not establish duplicate identity or shared acquisition. Evidence remains at
`artifacts/m2t3-scratch-investigation-TjTzhA/`. No broad similarity investigation
or dHash threshold change was made. Neither this heuristic nor the additional
constraint guarantees discovery of every acquisition relationship.

`approved-isolation-v1` extends `dhash-connected-components-v1` with explicit,
separate component-union constraints. Each approved constraint binds the original
candidate-plan digest, original candidate-graph digest, pre-amendment component
plan, exact-group/asset/pixel/alias/annotation lineage identities, and embedded
investigation evidence with checksums. The owner approval records this chat's
methodology authorization; it is not a completed visual review or a cryptographic
signature. Complete component membership is united before the unchanged seed-42
allocator runs. Official partition conflicts still fail closed.

Preparation, component packet generation and eventual export accept
`--isolation-constraints FILE --isolation-constraints-sha PINNED_SHA`. Both are
required when using the amendment. Changed bindings, pending approval, missing
or changed evidence, or mismatched identities are rejected. Export recomputes the
amended plan and requires the new packet's genuine completed review; an old
receipt cannot approve the new plan. Original graph and review files are preserved.
The constraint and its hash are retained in the plan, review binding and release
receipt. The old component and pair-review workflows remain compatible.

Verified evidence root: `artifacts/m2t3-final-isolation-BCvxnD/`.

- Constraint: `approved-isolation.json`, SHA-256
  `4af6862a012ba3a89f7626934f7cf669739d99122ed5b9e73eaf5a2d2d6079c9`.
- Plan: `plan-a/plan.json`, SHA-256
  `0585278c54569a17c98142fa80250bf649c872ce5f2405a8942486b27f369b69`.
- Packet: `packet-a/packet.json`, SHA-256
  `c324d4df23a9f4c879c7aa4b097ec64ee959b6acbc4e954c3043da94038732c3`.
- Allocation reproduced: 1287 train / 258 validation / 252 test, 1797 unique
  eligible assets, three unchanged exclusions, 1661 allocation groups and 24
  nontrivial components covering 160 images. All six classes in every split.
- Exactly 108 assignments changed, matching the approved simulation. Zero
  original candidate edges or additional isolation constraints cross splits.
- Both CLI entry points produced byte-identical plans and packets. Original
  source and annotation identities, 1083-edge graph and historical evidence are
  unchanged; 3601 files / 28208067 bytes still match T1.
- 72 focused regressions passed, including 17 preparation tests. Ruff lint,
  formatting, locked dependency and diff checks passed. Pending review exits 1.

`advisory-crosswalk.json` maps prior advisory observations to the new components.
Prior split labels there are historical. No human approval is transferred; all
24 decisions start pending. Open `packet-a/index.html`, inspect all component
members and boxes, edit only `packet-a/component-review.json`, and supply genuine
`accept_isolation`/`unresolved` decisions and notes, actual reviewer, a
 timezone-qualified completion timestamp, and methodology confirmation.

From the repository root, validate using:

```zsh
uv run --locked visionq check-component-review \
  --packet artifacts/m2t3-final-isolation-BCvxnD/packet-a \
  --packet-sha c324d4df23a9f4c879c7aa4b097ec64ee959b6acbc4e954c3043da94038732c3
```

M2.T3 remains open. Final owner review, a passing new receipt, final DQ08
acceptance, membership freeze and reproducible verified export remain required.
No final training inputs were generated.
