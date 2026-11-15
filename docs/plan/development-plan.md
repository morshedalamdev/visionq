# Development plan from zero to submission

Replanned **13 November 2026** after Azure access was confirmed. The user reconfirmed **project and report completion by 30 November**, with December rehearsal and defense approximately in its second week. The previous October windows and November 25 internal target are superseded by the conditional schedule below. If the university requires earlier submission, that takes precedence. No implementation or passed task evidence was found in this checkout; reconcile any work done elsewhere before recreating it.

Six modules still contain **22 tasks**. Azure and lightweight CI are integrated into existing tasks, not a separate platform module. The original estimate was 146–184 focused hours; allow approximately **152–196 hours** with the bounded Azure additions, excluding unmeasured teaching/retry overhead and unattended training. Across November 13–30 inclusive, that is about **8.4–10.9 focused hours/day**. The user can prioritize VisionQ full-time, but this is a high-risk stretch forecast with little buffer, not a delivery guarantee. Recalibrate after M1 using actual learning/application/test time. Azure does not remove the implementation critical path.

Read the [Azure/student-services plan](../design/azure-and-student-services.md): same Docker stack on one on-demand VM, private Blob backups, local fallback, credit/quotas checked first. Thesis delivery ends in November; the separate operation/retention plan continues until November 2027. Twelve-month Azure availability is not twelve months of continuous VM runtime.

**15 November runtime update:** use self-hosted vLLM for both AI roles. The 13–14 November M1 target has passed without a recorded gate; the dates below are the November 13 forecast, not evidence that M2 can begin. Reconcile any outside work and reforecast from the first unverified task. November 30 remains the delivery goal.

## Delivery and progression rule

Follow [WORKFLOW](../agent/WORKFLOW.md): the user implements; Codex explains what/why and supplies each file in ordered, explained code sections with exact placement instructions. One module occupies one chat; only one task is active. Deliver the complete current-task guide when practical, then review the user's test evidence. **All required task checks must pass before advancing**, and all task gates plus the module integration/regression gate must pass before closing its chat. Missing, skipped or failed results block progression. Track evidence in [TASK_LOG](../agent/TASK_LOG.md).

The dates below are sequential targets, never permission to skip a gate. Each active module records report/methodology/learning notes; M6 assembles them into the formal report. This Architecture chat handles design changes. The user opens the next module chat after handoff.

## Module 1 Foundation and feasibility

Conditional window: **13–14 November**. Estimate: 18–26 hours including Azure preflight/fixtures. Dependency: none.

| Task | Work and deliverable | Done when |
|---|---|---|
| M1.T1 | Establish scope, supervisor checklist, deadline/hardware/CPU-architecture inventory; retain Git, Python package, ignore/source inventory; check model terms and gated snapshot access before downloads, CPU instruction/dtype and platform-image compatibility, Azure region/quota/price/credit plan and GitHub status | Reproducible setup and recorded hardware/questions; Git preserved; model private-hosting terms checked; actual cloud cost/eligibility assumptions and unresolved supervisor items explicit; no GPU/free-VM promises |
| M1.T2 | Compose skeleton with private vLLM service URLs, PostgreSQL/pgvector migration, local artifact/config contracts; private Blob backup adapter with synthetic fixtures; lightweight GitHub Actions checks | Health/restart persistence passes; Blob private access, checksum round trip and interrupted-upload checks pass; CI evidence recorded without exposing secrets/data |
| M1.T3 | After preflight/model-term checks, run the two self-hosted vLLM services on the user-provisioned affordable VM; exercise schema-constrained generation, embeddings and MCP; repeat a local offline smoke check | All four checks below pass on the applied configuration, including five timed VM questions, private networking and deallocation |

Required M1.T3 evidence (the user runs the checks and shares results):

1. **Services and identity:** Start the generation and pooling servers together. Check their served aliases and actual chat/embedding requests. Save exact model revisions/file hashes, per-platform image digests, vLLM version, dtype, context/cache caps and Docker resource limits. Health alone does not pass.
2. **Retrieval and tool use:** Index a titled synthetic passage and an unrelated distractor, then embed a query through the same pooling endpoint. Verify finite, nonzero vectors of the pinned width and the expected passage ranks first by cosine similarity. Validate a real schema-constrained plan, execute one scoped metric tool through MCP and validate an answer against its fixture value. A failed endpoint must surface an error with no hosted fallback.
3. **VM feasibility:** With both services resident, all five scoped fixture questions must return schema-valid responses without OOM within 120 seconds **each, end to end**. Include at least one retrieval question and one metric question. Record per-question and median latency, combined peak RAM, relevant device, estimated/observed credit use, restricted SSH access and verified VM deallocation.
4. **Local fallback:** On the intended local Docker host, restart both cached services with external egress blocked and internal networking retained. From this fresh start, generate a schema-valid answer and embed a query using the mounted snapshots. Record evidence for both paths; results from the Azure VM do not pass this check.

M1.T3 is an early risk test, not a substitute for the final agent or evidence evaluation. Record introduction/related-work and learning notes inside M1; this does not open M6 early. Resolve smaller-model/hardware or Azure eligibility/cost failures before closing M1; a blocked cloud check is not a pass. Reforecast immediately if this window slips; do not hide learning overhead or remove required checks.

## Module 2 Dataset and reliable data pipeline

Conditional window: **15–17 November**. Estimate: 24–30 hours. Dependency: all M1 task and module gates passed.

| Task | Work and deliverable | Done when |
|---|---|---|
| M2.T1 | Acquire NEU-DET, record provenance/checksums/notices, inventory images/XML and source metadata | Dataset factsheet contains observed counts and unresolved source limits; original files are preserved |
| M2.T2 | Implement annotation adapter, class map, DQ01–DQ10, quarantine and review overlays/revisioned corrections | Every invalid fixture is handled as specified; five reviewed examples/class and box round-trip evidence are saved |
| M2.T3 | Group duplicates, freeze split manifest, standardize preprocessing and export model training inputs | No exact duplicate group crosses splits; train/validation/test memberships and transforms are hashed and audited |
| M2.T4 | Add resumable ingestion, run states, artifact/database reconciliation and a rights-reviewed catalog/manifest Blob backup | Repeat import changes no logical counts; interrupted import resumes; quality/lineage reports reproduce; restored catalog and artifact hashes match |

Gate target: released dataset v1, verified importer and frozen test membership by **17 November**. Record dataset/methodology notes from actual findings rather than planned assumptions. Check source rights before uploading dataset/model bytes to Azure.

## Module 3 Detector and traceable inference

Conditional window: **18–19 November**. Estimate: 18–24 hours excluding unattended training. Dependency: all M2 task and module gates passed. Choose the measured local/VM training device before runs; log hardware, cloud cost and checkpoint/prediction backups. GPU access is not assumed.

| Task | Work and deliverable | Done when |
|---|---|---|
| M3.T1 | Fine-tune YOLO11n baseline, log seeds/config/environment/checkpoints and validation learning curves | At least one valid trained model exists with complete provenance; leakage and conversion checks pass |
| M3.T2 | Select threshold/checkpoint using validation; freeze settings; evaluate held-out data and curate per-class failures | mAP50, mAP50–95, operating precision/recall and measured latency are saved with evaluator settings; no invented target accuracy |
| M3.T3 | Persist batch predictions, zero-detection success rows and failure coverage; support retry/resume and overlays | Stored box counts reconcile with exports; restart produces no duplicates; immutable batch/run evidence is available |

Gate target: detector and prediction snapshots available by **19 November**. During M3.T1, judge weakness using training/validation only and check labels, coordinates, splits and learning curves. Decide and finish the one bounded corrective training run **before any held-out test evaluation in M3.T2**. Freeze the model/settings, then test once. A post-test bug fix preserves the original result and is logged as a protocol deviation; further confirmed performance needs fresh untouched data, otherwise label the rerun exploratory. A low but honestly evaluated detector can still support the LLM systems study; do not claim industrial readiness. Passing this task means the evaluation protocol/implementation checks pass, not forcing the metric above an optimistic target.

## Module 4 Analytics RAG and MCP

Conditional window: **20–22 November**. Estimate: 24–30 hours. Dependency: all M3 task and module gates passed. Same contracts on Azure and local hosts; access the VM UI through the SSH tunnel.

| Task | Work and deliverable | Done when |
|---|---|---|
| M4.T1 | Implement canonical metric definitions, scoped SQL, API-owned consistent snapshots/evidence persistence and explicit paired-run comparisons | Hand-calculated fixtures match counts/ratios/deltas; concurrent run/quality changes cannot alter an answer snapshot; shared assets across versions/runs remain separate |
| M4.T2 | Prepare 10–20 approved documents; implement local embedding, versioned chunking, exact vector search and citations | A complete index can be rebuilt from its manifest; relevant development passages are retrieved; no QA/gold leakage |
| M4.T3 | Expose the five analytics/retrieval tools through the MCP server with read-only permissions and limits | The actual MCP client discovers and calls all tools; invalid scope, unapproved operation and timeout tests pass |
| M4.T4 | Build dataset/quality, inspection/overlay and persistent history/performance views; define the agent/evidence page using clearly labeled contract fixtures until M5 | Browse/filter/reopen stored runs and compare precision/recall/mAP percentages on labeled evaluation data; unlabeled accuracy is unavailable, confidence is distinct; chart values trace to sources and survive restart; no fixture is presented as live AI |

Gate target: metric/document evidence and real history/performance UI work by **22 November**. MCP is a required interface here, not a platform-building exercise. The live agent and saved AI-answer history connect in M5.T1; their M4 contract fixtures do not count as completed AI integration.

## Module 5 Local agent and LLM research

Conditional window: **23–26 November**. Estimate: 36–44 hours. Dependency: all M4 task and module gates passed. This is the main research module; benchmark preparation happens here, not in a parallel chat. Run all final LLM conditions on the same recorded hardware profile; moving hosts is not an unreported performance comparison.

| Task | Work and deliverable | Done when |
|---|---|---|
| M5.T1 | Implement and connect bounded planning, MCP tools, structured claims, verification, one repair/abstention and the live agent/evidence UI using development fixtures | Development questions have inspectable evidence; unsupported cases fail safely; original/final drafts persist; saved AI answers can be reopened after restart, with no fixture/live confusion |
| M5.T2 | Author 12 development and 48 held-out questions, independent gold facts, evidence labels and scoring rubric; freeze benchmark | Semantic families and data scopes are separated; benchmark/gold are excluded from RAG; freeze hashes and dates are recorded |
| M5.T3 | Implement RAG-only baseline and SQL+RAG without verification; freeze model/prompt/retrieval/budgets | All conditions run on the same frozen data and generator; the verifier ablation uses identical saved drafts/evidence |
| M5.T4 | Execute final LLM experiments, grade numeric and document claims, audit failures and analyze paired differences | Results include correctness, coverage, citations, abstention, retrieval and latency; independent review availability and study limits are disclosed |

Gate targets: M5.T1 uses development fixtures only; M5.T2 prepares separate development and untouched test families. Finish tuning and freeze the benchmark/system by **25 November**, only after M5.T3 checks pass; execute and grade final experiments by **26 November**. This tight window depends on measured runtime and preparation from earlier tasks. If gates slip, reforecast here rather than compressing away grading or protocol discipline. Do not repeatedly inspect held-out results to optimize prompts. Bug fixes after exposure require a recorded deviation and fresh confirmation questions or an exploratory label. Honest low model quality is distinct from a failing software check.

## Module 6 Integration report and defense

Conditional window: **27–30 November**. Estimate: 32–42 hours including Azure recovery/operations evidence. Dependency: all M5 task and module gates passed. Earlier modules supply their own report/learning notes; M6 is the single report assembly and final integration chat. Do not defer all writing until M6.

| Task | Work and deliverable | Done when |
|---|---|---|
| M6.T1 | Validate Compose workflow, offline inference, failure recovery, fresh local restore from Blob, access isolation, deallocation and resource/cost runbook | Cached local AI works offline; restored history/answers/counts/hashes match; cloud access/cost/deallocation checks have evidence |
| M6.T2 | Assemble report from earlier module notes: introduction, literature, requirements, data, architecture, methods and actual results | Full report draft target **28 November**, with actual results and no placeholders; fix M6.T1 failures first |
| M6.T3 | Complete figures/tables, limitations, reproducibility appendix, citation audit and proofreading; seek feedback | Submission-ready project/report target **29 November**; results trace to saved experiments; unavailable feedback is disclosed |
| M6.T4 | Prepare demo/slides/recording, source/reproduction package, final cost/resource ledger, December rehearsal and year-long retention/expiry handoff | Initial rehearsal and final package ready by **30 November** or earlier official deadline; actual submission tracked separately; later cleanup requires verified backups and user action |

## Calendar and critical path

| Dates | Main outcome | Report work |
|---|---|---|
| 13–14 Nov | M1 setup, Azure preflight/backup fixture and AI feasibility | Introduction/research questions |
| 15–17 Nov | M2 released dataset and reliable ingest | Related work/dataset/method notes |
| 18–19 Nov | M3 frozen detector and persisted predictions | Vision protocol and results notes |
| 20–22 Nov | M4 evidence tools and history/performance UI | Data contracts/retrieval notes |
| 23–25 Nov | M5 live agent, benchmark and final system freeze | LLM methods/rubric notes |
| 26 Nov | M5 final experiments and grading | Actual results/error analysis |
| 27–28 Nov | M6 integration/recovery gate then full draft | Assemble report and limitations |
| 29–30 Nov | M6 final review, package and initial rehearsal | Final project/report; submission by required date |
| 1–7 Dec | Additional rehearsal from frozen submission | No planned feature/research work |
| Approx. second week of Dec | Defense; exact date unconfirmed | Demonstrate and explain saved evidence |

Critical path: M1 hardware/Azure feasibility → M2 released data → M3 frozen predictions → M4 evidence tools/UI → M5 final evaluation → M6 report/package. Modules run sequentially in separate chats. Use unattended execution time for notes or explanation within the active task, not implementation of another module. There is no dependable schedule buffer in this rebaseline. Review the forecast at every module gate; a slip must trigger an explicit scope/capacity decision here while preserving the required LLM study and tests. Do not pretend dates remain achievable without evidence.

After the defense, follow the [twelve-month operation plan](../design/azure-and-student-services.md): verify archives, remove idle VM/disks/IP resources, retain compact Blob backups, check credit monthly and restore quarterly, and export before expiry. This is a maintenance horizon, not a seventh thesis module or automatic ongoing work by Codex.

## Scope control and exit criteria

Protect the LLM study, reliable image pipeline, MCP/RAG, local Docker operation and completed report. Cut cosmetic dashboard work, additional models, a second dataset, elaborate orchestration and extra training seeds first. Do not drop baselines, freeze discipline or honest failure reporting to add features. If hours available are materially below the estimate, reduce the question/tool vocabulary with the supervisor while retaining the core experiments; do not promise unchanged scope and deadline.

Completion means all 22 task gates and required module checks have passing evidence, the final report and reproducibility package are ready, and the defense can run locally. Research limitations must be disclosed but do not waive required software checks. A reviewer passing these planning documents does not mark any implementation task complete. Supply precise updates to [TASK_LOG](../agent/TASK_LOG.md) and [PROJECT_STATE](../agent/PROJECT_STATE.md) for the user to apply after each task/session; direct edits require delegation.
