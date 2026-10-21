# Development plan from zero to submission

Planning date: 21 October 2026. Required project/report completion: within November. Working final deadline: **30 November 2026**, with submission-ready materials by **25 November**. If the official submission date is earlier, move the internal dates earlier immediately. No implementation task is complete at the time this plan is written.

Six modules contain **22 tasks**. Each task has an observable result; small implementation steps belong inside these tasks rather than becoming dozens of additional modules. The total estimate is **146–184 focused hours**, about 26–33 hours/week across the remaining period. This is an estimate for one developer, excludes unexpected institutional delays, and must be recalibrated after M1. Unknown GPU availability is the largest early feasibility risk.

## Module 1 Foundation and feasibility

Window: 21–24 October. Estimate: 14–18 hours. Dependency: none.

| Task | Work and deliverable | Done when |
|---|---|---|
| M1.T1 | Establish scope, supervisor discussion checklist, actual submission date/hardware inventory; initialize Git, Python package, ignore rules and source/license inventory | A reproducible empty-project setup works; local hardware and research questions are recorded; unresolved supervisor items are explicit |
| M1.T2 | Create Compose skeleton, PostgreSQL/pgvector migration, artifact storage adapter and config contracts | Health checks pass; one fixture asset, a version and an artifact round-trip persist after restart |
| M1.T3 | Run the local AI feasibility spike: pull generator/embedding models, schema output, one typed metric tool and minimal MCP client/server round trip | Five simple fixture questions finish without OOM under the development time budget; actual versions/digests, latency and RAM are recorded |

M1.T3 is an early risk test, not a substitute for the final agent or evidence evaluation. Start the report's introduction/related-work notes now. If local AI is infeasible, resolve the smaller-model/hardware path before building the UI.

## Module 2 Dataset and reliable data pipeline

Window: 24–30 October. Estimate: 24–30 hours. Dependency: M1.T2; M1.T3 runs independently of real data.

| Task | Work and deliverable | Done when |
|---|---|---|
| M2.T1 | Acquire NEU-DET, record provenance/checksums/notices, inventory images/XML and source metadata | Dataset factsheet contains observed counts and unresolved source limits; original files are preserved |
| M2.T2 | Implement annotation adapter, class map, DQ01–DQ10, quarantine and review overlays/revisioned corrections | Every invalid fixture is handled as specified; five reviewed examples/class and box round-trip evidence are saved |
| M2.T3 | Group duplicates, freeze split manifest, standardize preprocessing and export model training inputs | No exact duplicate group crosses splits; train/validation/test memberships and transforms are hashed and audited |
| M2.T4 | Add resumable ingestion, run states and artifact/database reconciliation | A repeat import changes no logical counts; an interrupted import resumes; quality and lineage reports are reproducible |

Gate: released dataset v1, verified importer and frozen test membership by 30 October. Write the dataset/methodology section from actual findings rather than planned assumptions.

## Module 3 Detector and traceable inference

Window: 29 October–6 November. Estimate: 18–24 hours excluding unattended training. Dependency: M2.T3 for real training.

| Task | Work and deliverable | Done when |
|---|---|---|
| M3.T1 | Fine-tune YOLO11n baseline, log seeds/config/environment/checkpoints and validation learning curves | At least one valid trained model exists with complete provenance; leakage and conversion checks pass |
| M3.T2 | Select threshold/checkpoint using validation; freeze settings; evaluate held-out data and curate per-class failures | mAP50, mAP50–95, operating precision/recall and measured latency are saved with evaluator settings; no invented target accuracy |
| M3.T3 | Persist batch predictions, zero-detection success rows and failure coverage; support retry/resume and overlays | Stored box counts reconcile with exports; restart produces no duplicates; immutable batch/run evidence is available |

Gate: detector and prediction snapshots available by 6 November. During M3.T1, judge weakness using training/validation only and check labels, coordinates, splits and learning curves. Decide and finish the one bounded corrective training run **before any held-out test evaluation in M3.T2**. Freeze the model/settings, then test once. A post-test bug fix preserves the original result and is logged as a protocol deviation; further confirmed performance needs fresh untouched data, otherwise label the rerun exploratory. A low but honestly evaluated detector can still support the LLM systems study; do not claim industrial readiness.

## Module 4 Analytics RAG and MCP

Window: 29 October–11 November. Estimate: 24–30 hours. Fixture development can start after M1; real metric integration depends on M3.T3.

| Task | Work and deliverable | Done when |
|---|---|---|
| M4.T1 | Implement canonical metric definitions, scoped SQL, API-owned consistent snapshots/evidence persistence and explicit paired-run comparisons | Hand-calculated fixtures match counts/ratios/deltas; concurrent run/quality changes cannot alter an answer snapshot; shared assets across versions/runs remain separate |
| M4.T2 | Prepare 10–20 approved documents; implement local embedding, versioned chunking, exact vector search and citations | A complete index can be rebuilt from its manifest; relevant development passages are retrieved; no QA/gold leakage |
| M4.T3 | Expose the five analytics/retrieval tools through the MCP server with read-only permissions and limits | The actual MCP client discovers and calls all tools; invalid scope, unapproved operation and timeout tests pass |
| M4.T4 | Build dataset/quality, inspection/overlay, model comparison and agent/evidence views in Streamlit | User can trace a chart value or detection back to a run and source; replay labels and denominators are visible |

Gate: local metric + document evidence works end to end by 11 November. MCP is a required interface here, not a platform-building exercise.

## Module 5 Local agent and LLM research

Window: 28 October–18 November. Estimate: 36–44 hours. Start benchmark design on fixtures before M4 finishes. This is the main research module.

| Task | Work and deliverable | Done when |
|---|---|---|
| M5.T1 | Implement bounded planning, MCP tool use, structured claims, numeric/scope verification, document excerpts, one repair and abstention | Supported development questions produce inspectable evidence; ambiguous and unsupported cases fail safely; original/final drafts are retained |
| M5.T2 | Author 12 development and 48 held-out questions, independent gold facts, evidence labels and scoring rubric; freeze benchmark | Semantic families and data scopes are separated; benchmark/gold are excluded from RAG; freeze hashes and dates are recorded |
| M5.T3 | Implement RAG-only baseline and SQL+RAG without verification; freeze model/prompt/retrieval/budgets | All conditions run on the same frozen data and generator; the verifier ablation uses identical saved drafts/evidence |
| M5.T4 | Execute final LLM experiments, grade numeric and document claims, audit failures and analyze paired differences | Results include correctness, coverage, citations, abstention, retrieval and latency; independent review availability and study limits are disclosed |

Gate: candidate/prompt tuning ends by 11 November; benchmark is frozen by 12 November; final experiments finish by 18 November. Do not repeatedly inspect held-out results to optimize prompts. Bug fixes after exposure require a recorded protocol deviation and appropriately fresh confirmation questions, not an unmarked rerun presented as untouched test evidence.

## Module 6 Integration report and defense

Window: writing starts 21 October; final integration 16–30 November. Estimate: 30–38 hours.

| Task | Work and deliverable | Done when |
|---|---|---|
| M6.T1 | Validate complete Compose workflow, offline inference, persistence, failure recovery, backup/restore and resource budgets | A clean environment follows the runbook; cached local AI works with external network disabled; restored results match checksums |
| M6.T2 | Write the report continuously: introduction, literature, requirements, data, architecture and experiment methods first | Full report draft exists by 20 November with actual results inserted and no placeholder findings |
| M6.T3 | Complete figures/tables, limitations, reproducibility appendix and source/citation audit; obtain feedback and proofread | Submission-ready project and report exist by 25 November; each result traces to a saved experiment |
| M6.T4 | Prepare a short demo, slides, recorded backup, source/reproduction package and final submission checklist | Rehearsal succeeds; final package is ready by 30 November or the earlier confirmed university deadline; actual submission is tracked separately |

## Calendar and critical path

| Dates | Main outcome | Report work |
|---|---|---|
| 21–24 Oct | Environment, local AI/MCP feasibility and scope freeze | Introduction and research questions |
| 24–30 Oct | Dataset audit and released split | Related work and dataset section |
| 29 Oct–6 Nov | Detector training, evaluation and persistence; analytics fixtures | Vision methods and pipeline design |
| 28 Oct–11 Nov | QA design, RAG/MCP, agent and dashboard | LLM methods and evaluation protocol |
| 12–18 Nov | Frozen experiments, integration and grading | Results tables and error analysis |
| 19–20 Nov | Feature freeze and full report draft | Discussion and limitations |
| 21–25 Nov | Reproducibility review, corrections and report finalization | Submission-ready report |
| 26–30 Nov | Buffer, rehearsal, packaging and submission | Formatting/citation corrections only |

Critical path: M1 local feasibility → M2 released data → M3 frozen predictions → M4 evidence tools → M5 final evaluation → M6 report/package. The schedule overlaps activities, not people: use unattended training time for documents and the benchmark, and do not interpret overlapping windows as multiple full-time developers.

## Scope control and exit criteria

Protect the LLM study, reliable image pipeline, MCP/RAG, local Docker operation and completed report. Cut cosmetic dashboard work, additional models, a second dataset, elaborate orchestration and extra training seeds first. Do not drop baselines, freeze discipline or honest failure reporting to add features. If hours available are materially below the estimate, reduce the question/tool vocabulary with the supervisor while retaining the core experiments; do not promise unchanged scope and deadline.

Completion means all 22 tasks have linked artifacts/evidence, required checks have passed or disclosed limitations, the final report and reproducibility package are ready, and the defense can run locally. A reviewer passing these planning documents does not mark any implementation task complete. Update [PROJECT_STATE](../agent/PROJECT_STATE.md) after every development session.
