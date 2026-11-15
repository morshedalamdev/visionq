# VisionQ thesis project documentation

Last updated: **15 November 2026**. Original design and teaching workflow passed independent reviews; the Azure amendment also **passed after correction and recheck**, documented in the [review log](review/review-log.md). No application implementation task has passed. Preserve existing Git and user changes.

VisionQ will combine an industrial image data pipeline, a small supervised defect detector, and a self-hosted LLM agent that answers questions using database evidence and retrieved documents. The LLM is a main research contribution; RAG and a bounded MCP tool server support it. The reference Docker stack will run on an on-demand Azure VM with private Blob backups and a verified local fallback. vLLM serves Qwen for generation and EmbeddingGemma for document retrieval in separate private containers. M1 must verify that both models fit and work together on Azure and can restart offline on the local host.

The user reconfirmed **project/report completion by 30 November 2026**, rehearsal in December and defense around December's second week. The updated schedule is conditional on full-time progress and every required gate passing; it supersedes the elapsed October plan. Azure operation/retention is planned separately through **13 November 2027**. Portal observation confirmed $100 available for that entire period, not per month. Exact university dates, hardware, Azure capacity/prices and GitHub benefit activation still need checking.

## Read in this order

| Document | Purpose |
|---|---|
| [Topic and literature](research/topic-and-literature.md) | Topic assessment, supervisor repository audit, paper findings, research contribution and scope |
| [Dataset specification](research/dataset-specification.md) | NEU-DET facts, acquisition checks, annotation policy, splits and quality rules |
| [Architecture](design/architecture.md) | Components, data flow, storage contracts, local agent, MCP, RAG and deployment |
| [Technology stack](design/technology-stack.md) | Required tools, model candidates, hardware assumptions and version policy |
| [Azure and student services](design/azure-and-student-services.md) | Verified credit, same-stack deployment, private backups, costs, GitHub benefits and twelve-month operation |
| [Development plan](plan/development-plan.md) | Six modules with 22 tasks, dependencies, acceptance criteria and November schedule |
| [Evaluation and thesis](plan/evaluation-and-thesis.md) | Experiments, LLM baselines, metrics, thesis outline and defense demonstration |
| [Guided workflow and module kickoff](agent/WORKFLOW.md) | User implements; Codex teaches each file section, supplies code/instructions and reviews each task's test gate |
| [Agent project state](agent/PROJECT_STATE.md) | Current truth, next task, decisions and handoff procedure for another Codex chat |
| [Task gates and handoffs](agent/TASK_LOG.md) | All 22 task statuses, required-check evidence and module completion records |
| [Review record](review/review-log.md) | Independent challenge, corrections and final review verdict |

The original [Thesis Proposal.docx](Thesis%20Proposal.docx) is retained as supplied. It contains three candidate topics; this plan develops **Topic 3**. It is source material, not the current implementation specification.

## Documentation structure

```text
docs/
  README.md
  Thesis Proposal.docx                  original, unchanged
  research/
    topic-and-literature.md
    dataset-specification.md
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
  review/
    review-log.md
```

## Project boundary

The required result is a reproducible self-hosted research prototype with Azure deployment and local recovery, an evaluated LLM system, and a completed thesis report. It does not require a new detector architecture or a general agent platform. A single bounded agent selects tools, obtains evidence, drafts an answer and verifies its claims. Expand only if an experiment exposes a concrete unmet need. Azure eligibility/cost failures require explicit replanning; the credit is not a promise of GPU availability or continuous year-long hosting.

The detector predicts **known defect classes and bounding boxes**. The agent explains recorded results and documented limitations; it does not certify products, infer factory root causes, or turn missing timestamps into production trends. Proposed targets throughout these documents are acceptance goals, not measured results.

## Guided implementation

The designated chat recorded in WORKFLOW acts as the Architecture agent. The user opens **one chat per module** and implements the work themselves. Codex explains what and why, then supplies every file in ordered logical code sections with exact placement and tests. All required task tests must pass before the next task begins. Report notes stay with each active module; delivery is sequential through M1–M6.

Read the [workflow/kickoff](agent/WORKFLOW.md) and [agent state](agent/PROJECT_STATE.md), then open the M1 chat for **M1.T1**. No runnable application, dataset download, model checkpoint, dependency lock, database, Docker deployment, or benchmark result exists yet. Planned commands and paths describe work to implement, not working features.
