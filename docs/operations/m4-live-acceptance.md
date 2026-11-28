# M4 live acceptance — 26 November 2026

Status: **open; visual browser acceptance blocked by automation infrastructure**.
Implementation and live verification were explicitly delegated by the owner.
Baseline observed during acceptance: `278c1acfd3346bb3b839a2cd527cac4574f497f0`.
No commit/push or M5 implementation was performed.

## Local real evidence

Evidence directory: `artifacts/m4-live-20261126/` (local-only; contains restricted
API responses and must not be uploaded). `private-config.json` is mode 0600 and
contains local credentials; it is excluded from the evidence seal.

Verified source is loopback port 50071, database `visionq_t4_test`, released
NEU-DET v1 dataset `dc3b8671-354c-5393-930a-0e98cb0c04fd`, release manifest
`a8c14d88958f29a3042ba8b925584a9d6c770f60979cedb8bf9817ed393dc3c6`.
Migration `0008_detector_evidence` was already applied; no migration was rerun.
The saved source env had a stale port; runtime configuration overrides only it.
Artifact root is `artifacts/m2t4-real-9Sm1lP/catalog-artifacts`.

The absent `visionq_mcp` role was created with the existing SQL policy: SELECT,
no table writes, default read-only transactions, five-second statement timeout.
API and MCP were launched on loopback 8000/8001; Vite on loopback 5173.
The persistent MCP profile remains deterministic; a temporary real-embedding
MCP server was used only for approved application queries and then shut down.

Actual HTTP and MCP checks matched PostgreSQL: 252 successful image results,
553 detections,20 zero-detection successes,252 authenticated PNG overlays.
All overlay requests without credentials were denied. Every per-image detection
field matched SQL. Both authoritative registered research identities and all
exposed result fields matched stored payloads. API/MCP provenance and metric
responses agreed. All five tools passed; paired comparison used the same real
scope on both sides as a zero-difference control, not an independent experiment.
An incorrect corpus pin was rejected.

The dashboard now consumes each scope's optional `evaluation_links`, retaining
historical unavailable states and explicit synthetic/real labels. It displays
aggregate/per-class results, percentage and original fraction values, timing
stages, hardware/settings, identities and limitations directly from records.
The API already preserved these fields; no replacement API contract was needed.

Real capture exposed two fixture-sized safeguards: 200 findings and 512 KiB.
Bounds are now 5,000 findings and 8 MiB; complete capture and rejection beyond
the bounds remain mandatory. The real catalog has 3,779 retained findings.
Historical snapshots and frozen M2/M3 records were not rewritten.

## Approved remote scope and live results

Owner explicitly answered “Authorize this application-only scope” on 26 November.
Ten newly written application-operation documents and generic questions are
approved. Exact text, source hashes, manifest and approval record are under
`corpus/`. No dataset rows, names/IDs, measured detector results, images,
annotations, per-image evidence, source excerpts or backups enter remote inputs.
The corpus is separate from detector evidence and future M5 withheld evaluation.

Existing Azure containers reported healthy; `/v1/models` returned
`qwen3-4b-instruct-2507` and `embeddinggemma-300m`. Existing SSH key and verified
host connection forwarded loopback 18080/18081 to private model containers.
No resource provisioning, VM power operation or remote container restart occurred.
Model identities reuse the pinned M1 revisions; model listing alone does not
re-attest on-disk model hashes. The recorded M1 runtime evidence remains the pin.

Live EmbeddingGemma produced a verified 768-dimensional index with ten documents,
ten chunks and ten embeddings. Four generic questions retrieved expected source
passages; saved citation hashes matched chunk text. Qwen answered all four with
the correct document-key citations. Missing metrics were described as unavailable;
uploads did not imply inference; citations identified their provenance; overlays
did not establish manufacturing causes. Unsupported production yield returned
“Unavailable”. Retrieval-plus-generation times:51.907,50.266,37.341,50.307 seconds.
These are application-only development acceptance observations, not research
scores or live answers about restricted detector evidence. Full requests and
responses are retained locally. No agent orchestration is claimed before M5.

## Verification and remaining gate

Strict Python regression:333 passed,zero skipped,65.64 seconds. Frontend:12 tests
passed; TypeScript and production build passed. Ruff and diff checks passed.
New regressions cover real-size complete quality evidence, oversized rejection,
unavailable research evidence, fixture labels and registered metric rendering.
Independent live index rebuild produced ten documents/chunks/embeddings and
matched ranked chunk hashes; authenticated API retrieval passed. After a local
API restart, the saved snapshot was identical,252 successes remained and the
checked overlay response hash was unchanged. Browser reopening is still unverified.

Initial failures are retained: stale env port; real snapshot bounds; verifier SDK
field naming; ambiguous paired verifier scope. The corrected local and five-tool
checks passed. A frontend command first ran from the wrong directory; rerun from
`src/web` passed.

Browser automation failed twice with kernel timeout, including its surface
inventory call. Therefore real visual inspection, navigation/reopen and overlay
rendering are NOT passed by unit tests or authenticated image downloads. M4 must
remain open. Resume the real browser smoke using the running local dashboard,
select the released dataset/run, capture analytics, inspect class/hardware values,
open overlays, reopen stored history and verify unavailable/synthetic states.
Do not infer M4 closure or start M5 until that mandatory gate is observed.

## Conditional exact M5.T1 kickoff

After M4's remaining gate passes, open the M5 chat with:

> Work on VisionQ M5.T1 only. Read AGENTS.md, docs/agent/WORKFLOW.md,
> PROJECT_STATE.md, TASK_LOG.md, development-plan.md and
> docs/operations/m4-live-acceptance.md plus its final closure amendment.
> Connect the existing bounded MCP tools to planning, structured claims,
> evidence verification, one repair/abstention and persistent original/final
> answer history with the live agent/evidence UI. Use development questions only;
> do not prepare or inspect held-out M5.T2–T4 questions. Preserve private local
> detector evidence and the owner-approved application-only remote input scope.
> Remote real-detector answers require a separate rights decision or an authorized
> local model route. Reuse existing services; no cloud provisioning, power changes,
> frozen M2/M3 changes, commit or push. Follow the manual teaching workflow unless
> the owner explicitly delegates implementation. Verify all M5.T1 checks and
> saved-answer restart persistence before advancing within M5.


## Manual acceptance — 28 November 2026

Owner-reported manual browser acceptance: synthetic run history; successful,
failed and partial analytics; paired-run comparisons; unavailable-evidence
handling; real NEU-DET v1 analytics; 252 processed, zero failures, 553 detections,
232 images with predictions; authoritative evaluation/performance metrics,
manifest identities and detector provenance; 44 real inspection screenshots;
all six classes with boxes, confidence labels and persisted details; successful
zero-detection states; correct real/synthetic labels.
Real run: `fe274f2d-4def-575b-8aa1-a46c04f61624`.

Preserved 44 PNGs from /Users/morshedalam/Downloads/ii under
artifacts/m4-manual-20261128/screenshots with source/destination SHA-256 manifest.
Copies verified byte-identical. Screenshot review findings above are attributed
to the owner; Codex has not independently visually reviewed all 44 images.

Retained prior acceptance: strict Python 333 passed/zero skips; frontend 12 tests
and build passed; API/MCP/SQL agreement; authenticated overlays; five MCP tools;
live approved application-only retrieval and four cited Qwen answers plus
unsupported-yield abstention; persisted snapshot/run/image identity after API
restart. Targeted UI correction: two metric tests passed and diff check passed.
No full suite, training, evaluation, Azure operation or restricted transfer repeated.

Remaining mandatory check: actual real Run history -> Reopen inspection interaction.
Source wiring is present (History.onInspect -> App runId -> Inspection.initialRunId),
but source inspection is not browser acceptance. CUA timed out on 28 November.
M4 remains open ONLY pending this explicit browser confirmation; do not start M5.
At http://127.0.0.1:5173/ open Run history, Next datasets four times (current
100-record pages), select NEU-DET v1, locate fe274f2d (252 succeeded, zero failed),
click Reopen inspection; confirm the same run, released NEU-DET/test identity,
persisted image and detections load. Navigate away and repeat to confirm reopening.
Record actual result before marking M4 passed. No further regression rerun required
unless this exposes a defect.

M6 non-blocking UI backlog: structured evaluation dashboard; per-class tables and
charts; bounding-box label clipping/overlap; readable metric names and numeric
formatting; hide unnecessary internal paths; real dataset discoverability.
These do not invalidate the owner's accepted evidence semantics.

M5.T1 kickoff remains conditional on the final reopening check; use the exact
kickoff in docs/operations/m4-live-acceptance.md. M5 implementation not started.
