# VisionQ thesis project documentation

Last updated: **17 November 2026**. **Next: M2 — Dataset Ingestion and Validation, starting with M2.T1 on the Mac.** M1.T1 is complete under its recorded scope; M1.T2 passed all eight checks at `81f563a`. M1.T3 is deferred and the M1 integration gate remains open. See the [development sequence](plan/development-plan.md) and [task evidence](agent/TASK_LOG.md).

VisionQ will combine an industrial image data pipeline, a small supervised defect detector, and a self-hosted LLM agent that answers questions using database evidence and retrieved documents. The LLM is a main research contribution; RAG and a bounded MCP tool server support it. The reference Docker stack will run on an on-demand Azure VM with private Blob backups and a verified local fallback. Resumed M1.T3 must demonstrate that separate private vLLM containers for Qwen generation and EmbeddingGemma retrieval work together on Azure and can restart offline on the Mac.

The project/report deadline is **30 November 2026**, with rehearsal in December and defense around its second week. The [17 November Azure preflight](design/azure-and-student-services.md) recorded $100 remaining, credit expiry **12 November 2028**, and a planned compute share of about $55. The separate operations plan runs through **13 November 2027**. No VM was provisioned; capacity at deployment, CPU inference compatibility and timings remain unknown. Reforecast at each gate; deferring the VM saves credit but leaves less time to resolve model or hardware problems.

## Read in this order

| Document | Purpose |
|---|---|
| [Topic and literature](research/topic-and-literature.md) | Topic assessment, supervisor repository audit, paper findings, research contribution and scope |
| [Dataset specification](research/dataset-specification.md) | NEU-DET facts, acquisition checks, annotation policy, splits and quality rules |
| [Source inventory](research/source-inventory.md) | Model revisions, source/license evidence and the existing local dataset copy |
| [Architecture](design/architecture.md) | Components, data flow, storage contracts, local agent, MCP, RAG and deployment |
| [Technology stack](design/technology-stack.md) | Required tools, model candidates, hardware assumptions and version policy |
| [Azure and student services](design/azure-and-student-services.md) | Verified credit, same-stack deployment, private backups, costs, GitHub benefits and twelve-month operation |
| [Development plan](plan/development-plan.md) | Six modules with 22 tasks, dependencies, acceptance criteria and November schedule |
| [Evaluation and thesis](plan/evaluation-and-thesis.md) | Experiments, LLM baselines, metrics, thesis outline and defense demonstration |
| [Guided workflow and module kickoff](agent/WORKFLOW.md) | User implements; Codex teaches each file section, supplies code/instructions and reviews each task's test gate |
| [Agent project state](agent/PROJECT_STATE.md) | Current truth, next task, decisions and handoff procedure for another Codex chat |
| [Task gates and handoffs](agent/TASK_LOG.md) | All 22 task statuses, required-check evidence and module completion records |
| [Review record](review/review-log.md) | Independent challenge, corrections and final review verdict |
| [Catalog runbook](operations/catalog-runbook.md) | M2.T4 ingestion, reconciliation, backup/restore failure recovery, disposable PostgreSQL setup and rights limits |

The original [Thesis Proposal.docx](Thesis%20Proposal.docx) is retained as supplied. It contains three candidate topics; this plan develops **Topic 3**. It is source material, not the current implementation specification.

## Documentation structure

```text
docs/
  README.md
  Thesis Proposal.docx                  original, unchanged
  research/
    topic-and-literature.md
    dataset-specification.md
    source-inventory.md
  design/
    architecture.md
    technology-stack.md
    azure-and-student-services.md
  plan/
    development-plan.md
    evaluation-and-thesis.md
  agent/
    WORKFLOW.md
    PROJECT_STATE.md
    TASK_LOG.md
    M1_FOUNDATION.md
  review/
    review-log.md
```

## Project boundary

The required result is a reproducible self-hosted research prototype with Azure deployment and local recovery, an evaluated LLM system, and a completed thesis report. It does not require a new detector architecture or a general agent platform. A single bounded agent selects tools, obtains evidence, drafts an answer and verifies its claims. Expand only if an experiment exposes a concrete unmet need. Azure eligibility/cost failures require explicit replanning; the credit is not a promise of GPU availability or continuous year-long hosting.

The detector predicts **known defect classes and bounding boxes**. The agent explains recorded results and documented limitations; it does not certify products, infer factory root causes, or turn missing timestamps into production trends. Proposed targets throughout these documents are acceptance goals, not measured results.

## Guided implementation

The designated chat recorded in WORKFLOW acts as the Architecture agent. The user opens **one chat per module** and implements the work themselves. Codex explains each file section and its purpose, gives its exact placement, and reviews the user's test evidence. One task is active at a time. The [development plan](plan/development-plan.md) specifies when to return to the parked M1 and M4 chats; neither module closes before its integration checks pass.

Read the [workflow](agent/WORKFLOW.md) and [project state](agent/PROJECT_STATE.md), then open the M2 chat for **M2.T1**. Start with the existing local NEU-DET copy; provenance, observed counts, annotations and any supplied split still need auditing. Build the dataset, YOLO11n detector, analytics API and dashboard locally. Resume M1.T3 after M4.T1/T4 and before live retrieval, MCP integration or the LLM study. Clearly label any development fixture; it is not research evidence.
