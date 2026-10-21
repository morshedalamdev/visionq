# Development plan from zero to submission

Planning date: 21 October 2026. Required project/report completion: within November. Working final deadline: **30 November 2026**, with submission-ready materials by **25 November**. If the official submission date is earlier, move the internal dates earlier immediately. No implementation task is complete at the time this plan is written.

Six modules contain **22 tasks**. Each task has an observable result; code sections belong inside these tasks rather than becoming additional modules. The original estimate is **146–184 focused hours**, about 26–33 hours/week across the remaining period. Recalibrate after M1 for the user's learning, manual application and test-review pace; instruction time and retries have not been separately measured. Unknown GPU availability is the largest early feasibility risk.

## Delivery and progression rule

Follow [WORKFLOW](../agent/WORKFLOW.md): the user implements; Codex explains what/why and supplies each file in ordered, explained code sections with exact placement instructions. One module occupies one chat; only one task is active. Deliver the complete current-task guide when practical, then review the user's test evidence. **All required task checks must pass before advancing**, and all task gates plus the module integration/regression gate must pass before closing its chat. Missing, skipped or failed results block progression. Track evidence in [TASK_LOG](../agent/TASK_LOG.md).

The dates below are sequential targets, never permission to skip a gate. Each active module records report/methodology/learning notes; M6 assembles them into the formal report. This Architecture chat handles design changes. The user opens the next module chat after handoff.

## Module 1 Foundation and feasibility

Window: 21–24 October. Estimate: 14–18 hours. Dependency: none.

| Task | Work and deliverable | Done when |
|---|---|---|
| M1.T1 | Establish scope, supervisor discussion checklist, actual submission date/hardware inventory; inspect/retain existing Git, establish Python package, ignore rules and source/license inventory | A reproducible project setup works; local hardware and research questions are recorded; existing Git/history are preserved; unresolved supervisor items are explicit |
| M1.T2 | Create Compose skeleton, PostgreSQL/pgvector migration, artifact storage adapter and config contracts | Health checks pass; one fixture asset, a version and an artifact round-trip persist after restart |
| M1.T3 | Run the local AI feasibility spike: pull generator/embedding models, schema output, one typed metric tool and minimal MCP client/server round trip | Five simple fixture questions finish without OOM under the development time budget; actual versions/digests, latency and RAM are recorded |

M1.T3 is an early risk test, not a substitute for the final agent or evidence evaluation. Record introduction/related-work and learning notes inside M1; this does not open M6 early. If local AI is infeasible, resolve the smaller-model/hardware path before closing M1.

## Module 2 Dataset and reliable data pipeline

Window: 25–29 October. Estimate: 24–30 hours. Dependency: all M1 task and module gates passed.

| Task | Work and deliverable | Done when |
|---|---|---|
| M2.T1 | Acquire NEU-DET, record provenance/checksums/notices, inventory images/XML and source metadata | Dataset factsheet contains observed counts and unresolved source limits; original files are preserved |
| M2.T2 | Implement annotation adapter, class map, DQ01–DQ10, quarantine and review overlays/revisioned corrections | Every invalid fixture is handled as specified; five reviewed examples/class and box round-trip evidence are saved |
| M2.T3 | Group duplicates, freeze split manifest, standardize preprocessing and export model training inputs | No exact duplicate group crosses splits; train/validation/test memberships and transforms are hashed and audited |
| M2.T4 | Add resumable ingestion, run states and artifact/database reconciliation | A repeat import changes no logical counts; an interrupted import resumes; quality and lineage reports are reproducible |

Gate: released dataset v1, verified importer and frozen test membership by 29 October. Record dataset/methodology notes from actual findings rather than planned assumptions.

## Module 3 Detector and traceable inference

Window: 30 October–3 November. Estimate: 18–24 hours excluding unattended training. Dependency: all M2 task and module gates passed.

| Task | Work and deliverable | Done when |
|---|---|---|
| M3.T1 | Fine-tune YOLO11n baseline, log seeds/config/environment/checkpoints and validation learning curves | At least one valid trained model exists with complete provenance; leakage and conversion checks pass |
| M3.T2 | Select threshold/checkpoint using validation; freeze settings; evaluate held-out data and curate per-class failures | mAP50, mAP50–95, operating precision/recall and measured latency are saved with evaluator settings; no invented target accuracy |
| M3.T3 | Persist batch predictions, zero-detection success rows and failure coverage; support retry/resume and overlays | Stored box counts reconcile with exports; restart produces no duplicates; immutable batch/run evidence is available |

Gate: detector and prediction snapshots available by 3 November. During M3.T1, judge weakness using training/validation only and check labels, coordinates, splits and learning curves. Decide and finish the one bounded corrective training run **before any held-out test evaluation in M3.T2**. Freeze the model/settings, then test once. A post-test bug fix preserves the original result and is logged as a protocol deviation; further confirmed performance needs fresh untouched data, otherwise label the rerun exploratory. A low but honestly evaluated detector can still support the LLM systems study; do not claim industrial readiness. Passing this task means the evaluation protocol/implementation checks pass, not forcing the metric above an optimistic target.

## Module 4 Analytics RAG and MCP

Window: 4–8 November. Estimate: 24–30 hours. Dependency: all M3 task and module gates passed.

| Task | Work and deliverable | Done when |
|---|---|---|
| M4.T1 | Implement canonical metric definitions, scoped SQL, API-owned consistent snapshots/evidence persistence and explicit paired-run comparisons | Hand-calculated fixtures match counts/ratios/deltas; concurrent run/quality changes cannot alter an answer snapshot; shared assets across versions/runs remain separate |
| M4.T2 | Prepare 10–20 approved documents; implement local embedding, versioned chunking, exact vector search and citations | A complete index can be rebuilt from its manifest; relevant development passages are retrieved; no QA/gold leakage |
| M4.T3 | Expose the five analytics/retrieval tools through the MCP server with read-only permissions and limits | The actual MCP client discovers and calls all tools; invalid scope, unapproved operation and timeout tests pass |
| M4.T4 | Build dataset/quality, inspection/overlay and persistent history/performance views; define the agent/evidence page using clearly labeled contract fixtures until M5 | Browse/filter/reopen stored runs and compare precision/recall/mAP percentages on labeled evaluation data; unlabeled accuracy is unavailable, confidence is distinct; chart values trace to sources and survive restart; no fixture is presented as live AI |

Gate: local metric/document evidence and real history/performance UI work by 8 November. MCP is a required interface here, not a platform-building exercise. The live agent and saved AI-answer history connect in M5.T1; their M4 contract fixtures do not count as completed AI integration.

## Module 5 Local agent and LLM research

Window: 9–18 November. Estimate: 36–44 hours. Dependency: all M4 task and module gates passed. This is the main research module; benchmark preparation happens here, not in a parallel chat.

| Task | Work and deliverable | Done when |
|---|---|---|
| M5.T1 | Implement and connect bounded planning, MCP tools, structured claims, verification, one repair/abstention and the live agent/evidence UI using development fixtures | Development questions have inspectable evidence; unsupported cases fail safely; original/final drafts persist; saved AI answers can be reopened after restart, with no fixture/live confusion |
| M5.T2 | Author 12 development and 48 held-out questions, independent gold facts, evidence labels and scoring rubric; freeze benchmark | Semantic families and data scopes are separated; benchmark/gold are excluded from RAG; freeze hashes and dates are recorded |
| M5.T3 | Implement RAG-only baseline and SQL+RAG without verification; freeze model/prompt/retrieval/budgets | All conditions run on the same frozen data and generator; the verifier ablation uses identical saved drafts/evidence |
| M5.T4 | Execute final LLM experiments, grade numeric and document claims, audit failures and analyze paired differences | Results include correctness, coverage, citations, abstention, retrieval and latency; independent review availability and study limits are disclosed |

Gate: M5.T1 uses development fixtures only; M5.T2 prepares separate development and untouched test families. Candidate/prompt tuning ends by 13 November, benchmark/system freeze is 14 November, and final experiments finish by 18 November. Do not repeatedly inspect held-out results to optimize prompts. Bug fixes after exposure require a recorded protocol deviation and appropriately fresh confirmation questions, not an unmarked rerun presented as untouched test evidence. Pass protocol/software checks honestly even when measured model quality misses a research goal.

## Module 6 Integration report and defense

Window: 19–30 November. Estimate: 30–38 hours. Dependency: all M5 task and module gates passed. Earlier modules supply their own report/learning notes; M6 is the single report assembly and final integration chat.

| Task | Work and deliverable | Done when |
|---|---|---|
| M6.T1 | Validate complete Compose workflow, offline inference, persistence, failure recovery, backup/restore and resource budgets | A clean environment follows the runbook; cached local AI works with external network disabled; restored results match checksums |
| M6.T2 | Assemble and complete the report from earlier module notes: introduction, literature, requirements, data, architecture, methods and actual results | Full report draft exists by 20 November with actual results and no placeholder findings; revise the target if M6.T1 needs fixes rather than bypassing its gate |
| M6.T3 | Complete figures/tables, limitations, reproducibility appendix and source/citation audit; obtain feedback and proofread | Submission-ready project and report exist by 25 November; each result traces to a saved experiment |
| M6.T4 | Prepare a short demo, slides, recorded backup, source/reproduction package and final submission checklist | Rehearsal succeeds; final package is ready by 30 November or the earlier confirmed university deadline; actual submission is tracked separately |

## Calendar and critical path

| Dates | Main outcome | Report work |
|---|---|---|
| 21–24 Oct | Environment, local AI/MCP feasibility and scope freeze | Introduction and research questions |
| 25–29 Oct | M2 dataset audit and released split | Related work and dataset notes |
| 30 Oct–3 Nov | M3 detector training, evaluation and persistence | Vision methods and pipeline notes |
| 4–8 Nov | M4 analytics, RAG, MCP and history/performance dashboard | Data contracts and retrieval notes |
| 9–14 Nov | M5 agent/UI integration, QA design and benchmark/system freeze | LLM methods and evaluation notes |
| 15–18 Nov | M5 frozen experiments and grading | Results tables and error analysis notes |
| 19–20 Nov | M6 integration gate, feature freeze and full report draft target | Assemble report, discussion and limitations |
| 21–25 Nov | Reproducibility review, corrections and report finalization | Submission-ready report |
| 26–30 Nov | Buffer, rehearsal, packaging and submission | Formatting/citation corrections only |

Critical path: M1 local feasibility → M2 released data → M3 frozen predictions → M4 evidence tools/UI → M5 final evaluation → M6 report/package. Modules run sequentially in separate chats. Use unattended execution time for notes or explanation within the active task, not implementation of another module. If test/review cycles take longer, update the forecast and discuss scope here; do not skip gates to preserve dates.

## Scope control and exit criteria

Protect the LLM study, reliable image pipeline, MCP/RAG, local Docker operation and completed report. Cut cosmetic dashboard work, additional models, a second dataset, elaborate orchestration and extra training seeds first. Do not drop baselines, freeze discipline or honest failure reporting to add features. If hours available are materially below the estimate, reduce the question/tool vocabulary with the supervisor while retaining the core experiments; do not promise unchanged scope and deadline.

Completion means all 22 task gates and required module checks have passing evidence, the final report and reproducibility package are ready, and the defense can run locally. Research limitations must be disclosed but do not waive required software checks. A reviewer passing these planning documents does not mark any implementation task complete. Supply precise updates to [TASK_LOG](../agent/TASK_LOG.md) and [PROJECT_STATE](../agent/PROJECT_STATE.md) for the user to apply after each task/session; direct edits require delegation.
