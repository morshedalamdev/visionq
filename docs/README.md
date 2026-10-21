# VisionQ thesis project documentation

Last updated: 21 October 2026. Status: original design passed two review rounds; the later user-led teaching workflow also passed an independent consistency review. No application implementation task has passed. Git has since been initialized and must be preserved.

VisionQ will combine an industrial image data pipeline, a small supervised defect detector, and a local LLM agent that answers questions using database evidence and retrieved documents. The LLM is a main research contribution. RAG and a bounded MCP tool server are included because they serve that contribution. All AI inference will run locally in Docker in the reference deployment.

The user requires the **project and written report to be completed within November 2026**, ahead of a December defense. The working final deadline is 30 November; the internal feature freeze is 20 November and submission-ready target is 25 November. The exact university submission date and available hardware remain unknown.

## Read in this order

| Document | Purpose |
|---|---|
| [Topic and literature](research/topic-and-literature.md) | Topic assessment, supervisor repository audit, paper findings, research contribution and scope |
| [Dataset specification](research/dataset-specification.md) | NEU-DET facts, acquisition checks, annotation policy, splits and quality rules |
| [Architecture](design/architecture.md) | Components, data flow, storage contracts, local agent, MCP, RAG and deployment |
| [Technology stack](design/technology-stack.md) | Required tools, model candidates, hardware assumptions and version policy |
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

The required result is a reproducible local research prototype, an evaluated LLM system, and a completed thesis report. It does not require a new detector architecture or a general agent platform. A single bounded agent is sufficient: it selects tools, obtains evidence, drafts an answer, and verifies its claims. Expand only if an experiment exposes a concrete need that cannot be met by that design.

The detector predicts **known defect classes and bounding boxes**. The agent explains recorded results and documented limitations; it does not certify products, infer factory root causes, or turn missing timestamps into production trends. Proposed targets throughout these documents are acceptance goals, not measured results.

## Guided implementation

The designated chat recorded in WORKFLOW acts as the Architecture agent. The user opens **one chat per module** and implements the work themselves. Codex explains what and why, then supplies every file in ordered logical code sections with exact placement and tests. All required task tests must pass before the next task begins. Report notes stay with each active module; delivery is sequential through M1–M6.

Read the [workflow/kickoff](agent/WORKFLOW.md) and [agent state](agent/PROJECT_STATE.md), then open the M1 chat for **M1.T1**. No runnable application, dataset download, model checkpoint, dependency lock, database, Docker deployment, or benchmark result exists yet. Planned commands and paths describe work to implement, not working features.
