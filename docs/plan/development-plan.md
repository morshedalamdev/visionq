# Development plan from zero to submission

The owner revised the execution order on **17 November 2026**. M1.T1 is
complete under its recorded scope and M1.T2 passed V01–V08 at `81f563a`.
M2/M3 synthetic development has advanced, but the M2 real release and the
real-data M3 gate remain open. M4.T1–T4 pass local synthetic-development
implementation and M4 is locally code-complete. The Docker build and private
Compose path were reverified on 22 November for ARM64 and AMD64. M1.T3 passed its Azure retrieval and benchmark checks. Azure serving identity is accepted under the revised procedure. M1.T3 and M1 closed under the revised initial-release criteria. Hosted [Foundation run 45581753576](https://github.com/morshedalamdev/visionq/actions/runs/45581753576) completed successfully at `be81df6`. Only documentation changed since the 321-test local pass at `8630367`. Next is M2.T3 human duplicate review and real release. V04 remains post-release. Public React authentication remains a separate deployment concern. The [task register](../agent/TASK_LOG.md) and
[M4 Azure readiness report](../operations/m4-azure-readiness.md) preserve the
underlying evidence.

The [25 November audit](../operations/m4-azure-readiness.md) records the
current checkout and software checks. The 22 November image and service smoke
remains historical evidence. The private M1.T3 preflight can proceed while
real dataset release and detector acceptance are outstanding.

Complete the project and report by **30 November 2026**, then rehearse in December for the approximate second-week defense. An earlier official submission date takes precedence. The November 13 forecast of 152–196 focused hours covered all 22 tasks across six modules. The earlier module windows have been superseded. The task sizes below are original estimates, and the November 28–29 report dates in M6 are internal targets. Use measured throughput and remaining work to revise the forecast at each handoff. The deadline is at risk if the real-model checks need hardware or configuration changes.

Build the pipeline, detector, database-backed analytics, dashboard and integration interfaces on the Mac. Preserve the existing private Blob resources. For the later VM, retain approximately **$55 for compute** within the **$100 student credit** recorded at preflight. The balance covers storage, experiments and contingency. The [Azure plan](../design/azure-and-student-services.md) records the preflight, spend assumptions and offline local fallback. The separate operations horizon runs through 13 November 2027.

## Delivery and progression rule

Follow the [guided workflow](../agent/WORKFLOW.md). The user implements and tests. Codex explains the purpose, placement and behavior of every file in ordered code sections. Use one chat per module and one active task at a time. Record passing results from the applied code before starting the next task. Missing, skipped or failed required checks keep the task open.

Two handoffs in the revised order leave a module open. After verified M1.T1/T2,
park M1 and open the M2 chat. On 21 November, the owner authorized the
model-independent M4.T1 kickoff after M3 synthetic-development completion while
retaining the real M3 gate as blocked. M4.T1 can use only labeled synthetic
database evidence. After M4.T1, the plan returns to the outstanding M2/M3 real
release and acceptance work rather than silently treating that gate as passed.
M4.T1 passed its local synthetic-development gate on 21 November with canonical
metrics, comparisons, repeatable-read snapshots, API ownership and immutable
evidence. Local implementation of M4.T2/M4.T3 is authorized with deterministic
fixtures and replaceable model adapters; live integration and acceptance remain
blocked until M1.T3 verifies the real embedding and generation services. Reassess
M2.T3 and the real M3 gate separately; do not let fixture-backed M4 success
silently close those real-data gates. Once local M4 implementation is complete,
resume the original M1 chat for M1.T3 and the M1 integration/regression gate,
then run live M4 retrieval/MCP integration and the M4 module gate. The other
modules close in the usual order once all task and module checks pass. Capture
report and learning notes within each active task. The user opens or returns to
the appropriate chat.

## Module 1 Foundation and feasibility

Original estimate 18–26 hours including preflight and fixtures. M1.T1/T2 are complete. M1.T1 closed with its account check V08 deferred by the owner; M1.T2's separately numbered V08 (Foundation CI) passed. The T1 source inventory and configuration-file check are not proof of access to the two full model snapshots. M1.T3 has resumed in the original M1 chat.

| Task | Work and deliverable | Done when |
|---|---|---|
| M1.T1 | Establish scope, supervisor checklist, deadline/hardware/CPU-architecture inventory; retain Git, Python package, ignore/source inventory; check model terms and gated snapshot access before downloads, CPU instruction/dtype and platform-image compatibility, Azure region/quota/price/credit plan and GitHub status | Reproducible setup and recorded hardware/questions; Git preserved; model private-hosting terms checked; actual cloud cost/eligibility assumptions and unresolved supervisor items explicit; no GPU/free-VM promises |
| M1.T2 | Compose skeleton with private vLLM service URLs, PostgreSQL/pgvector migration, local artifact/config contracts; private Blob backup adapter with synthetic fixtures; lightweight GitHub Actions checks | Health/restart persistence passes; Blob private access, checksum round trip and interrupted-upload checks pass; CI evidence recorded without exposing secrets/data |
| M1.T3 | After preflight/model-term checks, run the two self-hosted vLLM services on the user-provisioned affordable VM; exercise schema-constrained generation, embeddings and MCP | V01–V03 pass for the Azure deployment. V04 is deferred until after initial release by owner approval |

Stage 1 recorded Azure eligibility, quota, candidate VM, retail estimates and image availability. No VM was provisioned. Capacity at allocation, CPU inference compatibility and end-to-end latency are open. Preserve the separate [Azure preflight record](../design/azure-and-student-services.md).

On resumption, Stage 2 verifies access and terms for the pinned `Qwen/Qwen3-4B-Instruct-2507` and `google/embeddinggemma-300m` revisions, downloads the approved snapshots, creates SHA-256 manifests and stages the authorized files. Stage 3 covers the T3 dependencies, the scoped MCP metric path in `t3_probe.py`, its tests, `compose.t3.yaml` and CPU container preparation. Recheck budget, quota, capacity and authorization before provisioning. Collect the Azure checks on the actual services.

Required M1.T3 evidence (the user runs the checks and shares results):

1. **Services and identity:** Start the generation and pooling servers together. Check their served aliases and actual chat/embedding requests. Apply the owner-approved initial-release AMD64 identity procedure in the M1.T3 deployment checklist. Save exact model revisions/file hashes, vLLM version, dtype, context/cache caps and Docker resource limits. Health alone does not pass.
2. **Retrieval and tool use:** Index a titled synthetic passage and an unrelated distractor, then embed a query through the same pooling endpoint. Verify finite, nonzero vectors of the pinned width and the expected passage ranks first by cosine similarity. Validate a real schema-constrained plan, execute one scoped metric tool through MCP and validate an answer against its fixture value. A failed endpoint must surface an error with no hosted fallback.
3. **VM feasibility:** With both services resident, all five scoped fixture questions must return schema-valid responses without OOM within 120 seconds **each, end to end**. Include at least one retrieval question and one metric question. Record per-question and median latency, combined peak RAM, relevant device, estimated/observed credit use, restricted SSH access and verified VM deallocation.
4. **Local fallback (deferred until after initial release by owner approval):** On the intended local Docker host, restart both cached services with external egress blocked and internal networking retained. From this fresh start, generate a schema-valid answer and embed a query using the mounted snapshots. Record evidence for both paths; results from the Azure VM do not pass this check.

M1.T3 establishes feasibility for the later M4 integration and M5 research. Keep the separate full agent evaluation and post-release offline recovery demonstration. If the chosen CPU, RAM, model access, VM capacity or remaining credit blocks a required check, record the failure, revisit feasibility with the Architecture chat and reforecast. Any proposed model change needs an explicit decision. For initial release, M1 closes after V01–V03 and the separate integration/regression gate pass. V04 remains deferred. Azure is the primary live inference environment. Local development uses synthetic fixtures and mocked endpoints.

## Module 2 — Dataset Ingestion and Validation

Original estimate 24–30 hours. M2.T1 inventory was verified on 18 November. The open release work begins at M2.T3. The required foundation is the completed M1.T1/T2 package, storage/configuration contracts and verified persistence. The core pipeline runs locally without model inference. Check whether an archive, extracted files, notices or a local inventory already exist before acquiring a source copy or writing an adapter. Follow the [dataset specification](../research/dataset-specification.md).

| Task | Work and deliverable | Done when |
|---|---|---|
| M2.T1 | Acquire NEU-DET, record provenance/checksums/notices, inventory images/XML and source metadata | Dataset factsheet contains observed counts and unresolved source limits; original files are preserved |
| M2.T2 | Implement annotation adapter, class map, DQ01–DQ10, quarantine and review overlays/revisioned corrections | Every invalid fixture is handled as specified; five reviewed examples/class and box round-trip evidence are saved |
| M2.T3 | Group duplicates, freeze split manifest, standardize preprocessing and export model training inputs | No exact duplicate group crosses splits; train/validation/test memberships and transforms are hashed and audited |
| M2.T4 | Add resumable ingestion, run states, artifact/database reconciliation and a rights-reviewed catalog/manifest Blob backup | Repeat import changes no logical counts; interrupted import resumes; quality/lineage reports reproduce; restored catalog and artifact hashes match |

The M2 module gate requires released dataset v1, a verified importer and frozen test membership. Derive dataset/methodology notes from the observed files and audit results. M2.T4 uses the existing private Blob resources for its rights-reviewed catalog/manifest backup. Verify rights before uploading dataset/model bytes.

**M2.T4 status (19 November 2026): partial.** The synthetic-only importer, reconciliation, local rights-classified backup, fresh restore with explicit failure recovery, CLI and CI enforcement are implemented and verified on disposable PostgreSQL clusters; see the [catalog runbook](../operations/catalog-runbook.md). Acceptance on the real NEU-DET release (T3 release/freeze pending) and the Blob backup (rights review and Azure authorization pending) remains open and is not claimed.

## Module 3 Detector and traceable inference

Original estimate 18–24 hours excluding unattended training. Start after all M2 task and module gates pass. Develop and run the YOLO11n baseline on the measured Mac device. Record hardware, training configuration and checkpoint/prediction backups. Revisit device fit with the Architecture chat if measurements require a change.

**M3 status (21 November 2026): synthetic-development complete; real-data module
gate blocked.** M3.T1/T2/T3 pass the local synthetic training, frozen evaluation,
schema, persistence, restart, overlay and MPS smoke gates. The actual smoke used
the exact frozen 24-image M2 development release and preserved two failed attempts
before a successful third-attempt resume. Evidence and checksums are in
`TASK_LOG.md`. This does not release NEU-DET, establish real-model feasibility or
close M3: M2.T3 real release/freeze, real training/evaluation, real persisted
snapshots and hosted CI remain pending.

| Task | Work and deliverable | Done when |
|---|---|---|
| M3.T1 | Fine-tune YOLO11n baseline, log seeds/config/environment/checkpoints and validation learning curves | At least one valid trained model exists with complete provenance; leakage and conversion checks pass |
| M3.T2 | Select threshold/checkpoint using validation; freeze settings; evaluate held-out data and curate per-class failures | mAP50, mAP50–95, operating precision/recall and measured latency are saved with evaluator settings; no invented target accuracy |
| M3.T3 | Persist batch predictions, zero-detection success rows and failure coverage; support retry/resume and overlays | Stored box counts reconcile with exports; restart produces no duplicates; immutable batch/run evidence is available |

The M3 module gate requires the frozen detector and persisted prediction snapshots. During M3.T1, judge weakness using training/validation only and check labels, coordinates, splits and learning curves. Decide and finish the one bounded corrective training run **before any held-out test evaluation in M3.T2**. Freeze the model/settings, then test once. A post-test bug fix preserves the original result and is logged as a protocol deviation; further confirmed performance needs fresh untouched data, otherwise label the rerun exploratory. A low but honestly evaluated detector can still support the LLM systems study; do not claim industrial readiness. Passing this task means the evaluation protocol/implementation checks pass, not forcing the metric above an optimistic target.

## Module 4 Analytics RAG and MCP

Original estimate 24–30 hours. Synthetic M3 development and the M4.T1
local synthetic-development gate are complete. M4.T1 used labeled synthetic
database evidence. The full M3 real-data gate remains open and must be resumed
after M2.T3 real release/freeze. T1 supplies the metric and evidence contracts
for the real history/performance UI. T4 can build the agent/evidence view against
explicitly labeled fixtures, including the integration contracts it consumes.
Keep real detector measurements traceable to stored evaluation runs. M4.T2/T3
local implementation may use labeled deterministic fixtures and replaceable
model/service adapters. Their live acceptance checks stay blocked until M1.T3
verifies the pinned services. After local T2/T3 code passes, resume M1.T3 for
service verification, then run the remaining live M4 integration and module
gate. The production contracts apply on both hosts.

| Task | Work and deliverable | Done when |
|---|---|---|
| M4.T1 | Implement canonical metric definitions, scoped SQL, API-owned consistent snapshots/evidence persistence and explicit paired-run comparisons | Hand-calculated fixtures match counts/ratios/deltas; concurrent run/quality changes cannot alter an answer snapshot; shared assets across versions/runs remain separate |
| M4.T2 | Prepare 10–20 approved documents; implement local embedding, versioned chunking, exact vector search and citations | A complete index can be rebuilt from its manifest; relevant development passages are retrieved; no QA/gold leakage |
| M4.T3 | Expose the five analytics/retrieval tools through the MCP server with read-only permissions and limits | The actual MCP client discovers and calls all tools; invalid scope, unapproved operation and timeout tests pass |
| M4.T4 | Build dataset/quality, inspection/overlay and persistent history/performance views; define the agent/evidence page using clearly labeled contract fixtures until M5 | Browse/filter/reopen stored runs and compare precision/recall/mAP percentages on labeled evaluation data; unlabeled accuracy is unavailable, confidence is distinct; chart values trace to sources and survive restart; no fixture is presented as live AI |

### M4.T1 local synthetic closeout

M4.T1 reused the M3 synthetic inference snapshot and existing
catalog/inference constraints; do not add a UI, retrieval index, MCP server or
LLM integration in this task.

Implementation is recorded at `artifacts/m4t1-local-20261121/evidence.json`:
migration `0004_analytics`, canonical metrics and API-owned repeatable-read
snapshots pass on synthetic fixtures, immutable hashes survive concurrent
quality changes, and the full strict suite reports 255 passing tests. This is
local synthetic-development evidence, not real NEU-DET or live-model acceptance.

Required implementation shape:

1. one canonical analytics domain/service boundary;
2. parameterized, scoped SQL for the authoritative metric catalogue and explicit
   `pending`, `running`, `succeeded` and `failed` coverage;
3. a repeatable-read, API-owned snapshot containing metric, scope, provenance,
   threshold and dataset/run identity evidence;
4. immutable evidence persistence with a stable canonical SHA-256;
5. explicit left/right batch-run comparison compatibility and deterministic
   deltas;
6. independent hand-calculated fixtures covering zero denominator, zero boxes,
   partial runs, same asset across versions/runs, class filtering and concurrent
   state changes.

Required M4.T1 gate: hand calculations equal service outputs; an existing
snapshot survives concurrent run/quality mutations unchanged; incompatible
comparisons fail; shared assets remain separate across scope IDs; evidence
persistence failure is explicit; focused and strict PostgreSQL regressions pass.

### M4.T2 local synthetic closeout

M4.T2 may be implemented and verified locally before M1.T3. Local passage search
uses labeled deterministic fixtures through the same typed interface as the
future private EmbeddingGemma adapter. This passes software, isolation,
integrity and citation contracts only. Actual retrieval quality, model identity,
768-dimensional output, prefixes and Azure endpoint behavior remain live
acceptance checks blocked until M1.T3. No fixture result approves the production
corpus or substitutes for real model evidence.

The 21 November local gate passed using isolated synthetic documents and the
deterministic `visionq-hash-unigram-v1` backend. Migration `0005_retrieval`,
manifest/chunking/adapters, exact pgvector search, citations, interruption
resume, profile/version isolation and API validation passed 279 strict tests.
Evidence is recorded at `artifacts/m4t2-local-20261121/evidence.json`.
EmbeddingGemma identity, 768-dimensional vectors, real prefixes, relevance and
live endpoint behavior are still NOT_RUN.

### M4.T3 local synthetic closeout

The approved backward-compatible extension adds evidence-v2 MCP snapshots:
existing M4.T1 rows remain readable; new API-owned captures can pin an explicit
set of primary/left/right scopes, detailed quality findings and one ready
corpus/index pair. Migration `0006_mcp_evidence` adds the nullable retrieval
foreign key without rewriting historical evidence.

The official MCP SDK 2.3.x exposes exactly the five approved tools over
authenticated Streamable HTTP. A real SDK client discovers and calls every tool
against PostgreSQL/pgvector. The MCP service consumes immutable snapshot payloads,
uses the existing retrieval service only for the exact pinned index and has no
write route. Least-privilege role, timeout, invalid-scope, output-cap and
database-outage checks pass locally.

This is local synthetic-development evidence. It does not prove live
EmbeddingGemma retrieval quality, production corpus approval, Azure networking or
full M4 acceptance. M4.T4 may consume the typed, fixture-backed contracts while
those live checks remain explicit.

### M4.T4 local synthetic closeout

React/Vite is the approved frontend. The local application reads only from
authenticated FastAPI APIs and renders persisted dataset quality, batches,
run/history filters, original-coordinate detections, canonical snapshot metrics,
paired comparisons and explicitly labeled agent/evidence fixtures. Evaluation
accuracy remains unavailable until authoritative persisted evaluation rows
exist; synthetic evaluation artifacts are not promoted to UI measurements.

The owner-approved upload extension is a bounded request lifecycle, not a
background inference framework: PNG/JPEG bytes are decoded, size-limited,
content-addressed below the configured artifact root and persisted with an
explicit existing dataset/batch scope. The request is `ready` for review while
inference remains `not_started` or `pending_registration`. There is no automatic
catalog registration, queue or detector execution.

The local M4 gate is code-complete when FastAPI/PostgreSQL, React tests/build,
browser smoke, restart persistence and regression gates pass. Full M4 acceptance
still requires M1.T3 live services, real retrieval/MCP behavior, real M2/M3
evidence and the final integrated module gate.

At M4 closure, reconcile real database metrics, UI history and evidence with live embedding retrieval, citations and all five bounded MCP tools. A fixture-backed adapter can test wiring during core development. Only actual service results satisfy retrieval, MCP integration and AI evaluation requirements. M5.T1 connects the live agent and saved AI-answer history.

## Module 5 Local agent and LLM research

Original estimate 36–44 hours. Start after all M4 task and module gates pass, including the prerequisite resumed M1.T3 and M1 closure. This is the main research module; benchmark preparation happens here, not in a parallel chat. Run all final LLM conditions on the same recorded hardware profile; moving hosts is not an unreported performance comparison.

| Task | Work and deliverable | Done when |
|---|---|---|
| M5.T1 | Implement and connect bounded planning, MCP tools, structured claims, verification, one repair/abstention and the live agent/evidence UI using development fixtures | Development questions have inspectable evidence; unsupported cases fail safely; original/final drafts persist; saved AI answers can be reopened after restart, with no fixture/live confusion |
| M5.T2 | Author 12 development and 48 held-out questions, independent gold facts, evidence labels and scoring rubric; freeze benchmark | Semantic families and data scopes are separated; benchmark/gold are excluded from RAG; freeze hashes and dates are recorded |
| M5.T3 | Implement RAG-only baseline and SQL+RAG without verification; freeze model/prompt/retrieval/budgets | All conditions run on the same frozen data and generator; the verifier ablation uses identical saved drafts/evidence |
| M5.T4 | Execute final LLM experiments, grade numeric and document claims, audit failures and analyze paired differences | Results include correctness, coverage, citations, abstention, retrieval and latency; independent review availability and study limits are disclosed |

Gate targets: M5.T1 uses development fixtures only; M5.T2 prepares separate development and untouched test families. Finish development-only tuning and freeze the experimental system after M5.T3 checks pass. Execute and grade the final runs in M5.T4. Reforecast using measured runtime and grading workload. Do not repeatedly inspect held-out results to optimize prompts. Bug fixes after exposure require a recorded deviation and fresh confirmation questions or an exploratory label. Honest low model quality is distinct from a failing software check.

## Module 6 Integration report and defense

Original estimate 32–42 hours including Azure recovery/operations evidence. Start after all M5 task and module gates pass. Earlier modules supply their own report/learning notes; M6 is the single report assembly and final integration chat. Do not defer all writing until M6.

| Task | Work and deliverable | Done when |
|---|---|---|
| M6.T1 | Validate initial-release Compose workflow, failure recovery, fresh local restore from Blob, access isolation, deallocation and resource/cost runbook | Initial release requires restore and recovery checks. Verify both cached AI services restart and work offline after release. Restored history/answers/counts/hashes match; cloud access/cost/deallocation checks have evidence |
| M6.T2 | Assemble report from earlier module notes: introduction, literature, requirements, data, architecture, methods and actual results | Full report draft target **28 November**, with actual results and no placeholders; fix M6.T1 failures first |
| M6.T3 | Complete figures/tables, limitations, reproducibility appendix, citation audit and proofreading; seek feedback | Submission-ready project/report target **29 November**; results trace to saved experiments; unavailable feedback is disclosed |
| M6.T4 | Prepare demo/slides/recording, source/reproduction package, final cost/resource ledger, December rehearsal and year-long retention/expiry handoff | Initial rehearsal and final package ready by **30 November** or earlier official deadline; actual submission tracked separately; later cleanup requires verified backups and user action |

## Calendar and critical path

| Execution order | Exit evidence | Report work |
|---|---|---|
| Completed M1.T1 → M1.T2 | Foundation closeout, eight T2 gates and CI in the task register | Scope, hardware and setup record |
| Next M2.T1 → T2 → T3 → T4 → M2 gate | Observed factsheet, validated annotations, split release, resumable ingest and restore | Dataset, lineage and quality findings |
| M3 synthetic T1 → T2 → T3 complete; real M3 gate open | Frozen synthetic YOLO11n and persisted prediction snapshots; M2 real release still blocks real acceptance | Detector software methods and synthetic-development results |
| M4.T1 using labeled synthetic evidence, then reassess real M2/M3 gate | Metric snapshots and paired-scope contracts without model services | Database analytics evidence |
| M4.T4, then park M4 | Real run history/performance structure and fixture-labeled AI view | Database and UI evidence |
| Resume M1.T3 → M1 gate | Two verified Docker services, real retrieval and MCP metric probe, five timed VM questions (local offline restart deferred to post-release recovery) | Feasibility limits, resource use and cost |
| Resume M4.T2 → M4.T3 → M4 gate | Rebuildable real index, working bounded MCP service and evidence-linked UI | Retrieval and tool contracts |
| M5 → M5 gate | Agent integration, frozen benchmark, three evaluated arms and same-draft ablation | LLM methods, grading and failure analysis |
| M6 → M6 gate | Initial-release restore and recovery, reproducible experiments, final report and demo package by 30 November | Assemble and submit the project and report |
| 1–7 December, then approximate second week | Rehearsal from the frozen package, then defense | Explain and demonstrate saved evidence |

Track the critical path at each gate. If measured remaining work exceeds the time available before **30 November**, bring the estimate and scope tradeoffs to the Architecture chat immediately. Preserve the approved research baselines, post-release offline demonstration, reproducibility evidence and all required checks. The exact defense date remains unconfirmed.

After the defense, follow the [twelve-month operation plan](../design/azure-and-student-services.md): verify archives, remove idle VM/disks/IP resources, retain compact Blob backups, check credit monthly and restore quarterly, and export before expiry. This is a maintenance horizon, not a seventh thesis module or automatic ongoing work by Codex.

## Scope control and exit criteria

Protect the LLM study, reliable image pipeline, MCP/RAG, local Docker operation and completed report. Cut cosmetic dashboard work, additional models, a second dataset, elaborate orchestration and extra training seeds first. Do not drop baselines, freeze discipline or honest failure reporting to add features. If hours available are materially below the estimate, reduce the question/tool vocabulary with the supervisor while retaining the core experiments; do not promise unchanged scope and deadline.

Completion means all 22 task gates and required module checks have passing evidence, the final report and reproducibility package are ready, and the defense can run locally. Research limitations must be disclosed but do not waive required software checks. A reviewer passing these planning documents does not mark any implementation task complete. Supply precise updates to [TASK_LOG](../agent/TASK_LOG.md) and [PROJECT_STATE](../agent/PROJECT_STATE.md) for the user to apply after each task/session; direct edits require delegation.
