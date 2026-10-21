# Dataset specification and quality contract

Status: source-informed specification; the dataset archive has **not** been downloaded or audited. Complete the observed column during M2. See [literature P2 and P5](topic-and-literature.md) for citations and interpretation.

## Dataset factsheet

| Property | Published description or project policy | Observed archive value |
|---|---|---|
| Source | [Northeastern University dataset page](https://faculty.neu.edu.cn/songkechen/zh_CN/zdylm/263270/list/index.htm) | Not downloaded |
| Intended archive | NEU-DET, not image-only NEU-CLS | Pending |
| Task | Supervised known-defect detection with bounding boxes | Pending sample audit |
| Images | Published collection: 1,800 grayscale images, 200 × 200 pixels | Pending count, dimensions and channel scan |
| Composition | Published: 300 images per source category; six categories | Pending image and box counts per class |
| Annotation | XML, corner coordinates; multiple boxes may occur | Pending schema, indexing and endpoint inspection |
| Normal samples | No normal control class established by the documentation | Audit archive; do not assume any |
| Production context | Genuine timestamps, machine IDs and denominators not established | Missing unless verified in source metadata |
| Rights | Official page requests citation; explicit redistribution terms not established | Inspect bundled notices and record terms |
| Original paper split | 1,260 train / 540 test | Check for supplied split manifests |
| Project split | Grouped, approximately 70% train / 15% validation / 15% test | Publish actual counts after duplicate audit |
| Collection provenance | Use source description; unknown details stay unknown | Record download URL, date and archive SHA-256 |

Do not upload source images/labels to Git or redistribute the archive by default. Record the source and acquisition instructions. If use terms are unclear, obtain supervisor guidance before distributing data; this does not prevent building the framework on tiny self-created fixtures.

## Class vocabulary and annotation import

The following is the **project's proposed ID mapping**, not a claim about source IDs. Preserve source spellings and define aliases explicitly during import.

| ID | Canonical name |
|---|---|
| 0 | crazing |
| 1 | inclusion |
| 2 | patches |
| 3 | pitted_surface |
| 4 | rolled_in_scale |
| 5 | scratches |

Preserve the original XML and its checksum. Canonical boxes use zero-based, half-open pixel edges `[xmin, ymin, xmax, ymax)` in the original image orientation. Require `0 <= xmin < xmax <= width` and equivalent Y bounds. Source endpoint semantics are currently unknown: inspect border cases and draw at least five annotated images per class before selecting the conversion. If XML is verified as one-based inclusive, subtract one from each minimum and retain each maximum. Never infer this solely from the XML format name.

YOLO export uses `cx=(xmin+xmax)/(2W)`, `cy=(ymin+ymax)/(2H)`, `w=(xmax-xmin)/W`, `h=(ymax-ymin)/H`. Keep conversion tests for border boxes, tiny boxes and round trips. Human corrections create a new annotation revision with author/reason; they do not overwrite source evidence or promote predictions into labels. The MVP labeling feature is import, visual review and revisioned corrections, not a new annotation platform.

## Preprocessing and splitting

1. Preserve raw bytes. Extract file size, SHA-256, decoded width/height/channels, source relative path and annotation hash. Decode failure is a stored quality outcome.
2. Audit exact duplicates before splitting; canonicalize identical content and preserve all source-path aliases. Conflicting labels on identical pixels require review. Use perceptual hashes to flag near duplicates; review candidate groups without automatically deleting valid similar textures.
3. Freeze duplicate/acquisition groups. If real acquisition-group IDs exist, keep groups intact; otherwise document that independence beyond detected duplicates cannot be guaranteed.
4. Prefer verified official partitions if supplied: keep official test intact and derive validation from training groups. Otherwise use project-specific approximate 70/15/15 grouping, seed 42, stratification by source category with per-box class coverage checks. Never claim it matches the paper's 70/30 split. A clean 1,800-image archive would yield 1,260/270/270 before group constraints; actual counts may differ.
5. Freeze a manifest containing asset ID, raw hash, annotation hash/revision, group ID, split and class-map version. Hash the manifest. Release fails if any exact duplicate group crosses splits; near-duplicate exceptions require an explanation. Freeze test membership before model tuning.
6. Convert grayscale to three identical RGB channels for the detector. Use the model library's recorded resize/letterbox/normalization path; avoid a second hidden resizing pipeline. Store transform scale/padding so boxes can be mapped back to the original image. Try input size 320 in the first feasibility run; freeze the validated choice before experiments.
7. Apply training augmentation only to training images. Fit any learned preprocessing on training data only. Avoid contrast enhancement/denoising in the initial baseline because it changes the signal and creates an extra experiment.

No synthetic variants or augmented siblings enter a different split. Do not select the checkpoint, threshold or image size using test results.

## Validation rules

Rules are project adaptations of the validation principles in P4. Each finding records rule ID/version, severity, asset/batch, observed/expected values and action. Dataset release is separate from raw ingestion: invalid assets can be catalogued but cannot silently enter training.

| Rule | Check | Severity and action | Verification fixture |
|---|---|---|---|
| DQ01 | File safely decodes within byte/pixel limits | Error; quarantine | Truncated image and oversized header |
| DQ02 | Positive dimensions and expected source geometry/channels | Error on unusable input; warning on a documented variant | Zero size, RGB variant |
| DQ03 | Training/evaluation annotation exists and parses safely | Error; block affected sample | Missing XML, malformed XML, external entity |
| DQ04 | Class belongs to frozen vocabulary | Error; quarantine annotation | Unknown class and explicit alias |
| DQ05 | Finite, ordered, in-bounds nonempty box | Error; no silent clipping | Negative, reversed, NaN, border box |
| DQ06 | XML dimensions agree with decoded image | Error; review | Deliberate mismatch |
| DQ07 | Exact hash duplicates and label conflicts accounted for | Deduplicate aliases; error for conflicts | Same bytes at new paths |
| DQ08 | No duplicate/acquisition group spans splits | Error; block release | Shared group across train/test |
| DQ09 | Released artifact checksum matches manifest | Error; block run | Changed bytes after registration |
| DQ10 | Class coverage/count and brightness statistics compared with reference | Warning; review, no automatic deletion | Shifted batch and absent class |

An empty annotation is not evidence of a good product in this source. Label-free inference uploads may omit labels and must be tagged `unlabeled`; supervised training/evaluation requires the appropriate annotation policy. Distinguish legitimate empty predictions from missing prediction records.

## Batches and analytical meaning

Define deterministic replay batches from manifest IDs after splitting; record `batch_kind=synthetic_replay`, seed and membership hash. Keep `source_event_time` null unless authentic, `ingested_at` as actual processing time, and any `simulated_event_time` in a separate field. Prefer batch IDs on charts over simulated dates.

Define metrics before queries: annotated box count, predicted box count, images with at least one prediction, successfully processed image count, quarantined count, and unique image count per class. An image may contribute to several classes; summing per-class image counts can exceed the total. Ratios use the exact denominator and named prediction threshold.

Do not report manufacturing yield, real defect prevalence, factory drift or causal explanations. Box area is a rectangular image-space proxy, not segmented defect area, physical dimensions or severity. A zero-box prediction means the detector returned no box above its threshold; it does not establish that the item is healthy.
