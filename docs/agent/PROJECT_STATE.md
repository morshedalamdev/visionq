# VisionQ agent handoff and project state

Last updated: 21 October 2026, Asia/Shanghai. This is the canonical continuation record. Read it with [WORKFLOW](WORKFLOW.md) and [TASK_LOG](TASK_LOG.md) before assisting in a new chat; check the filesystem rather than assuming this snapshot is still current.

## User intent and binding requirements

- Final-year thesis with December graduation/defense; **project and report must be completed during November 2026**. Working deadline 30 November, submission-ready target 25 November; exact institutional date is not known.
- Original topic: A Data Engineering Framework for Industrial Visual Defect Detection Using Machine Learning.
- Combine data engineering, software engineering and a **major LLM research contribution**. LLM work is not an optional reporting extra.
- Run the AI locally in Docker. No hosted LLM, paid API or cloud spending has been requested.
- MCP/RAG should be included when they fit, not inserted just for terminology and not left as optional if useful. Current design includes document RAG and a small five-tool MCP server as required components.
- A general agent platform may be built only if needed. Current requirements are met by a single bounded agent; no need has been identified for a general platform.
- The user requested a documentation plan first, followed by independent subagent challenge/review and correction until passed. Do not confuse that planning review with implementation validation.
- The user implements all work manually. Codex supplies teaching, code sections, exact edit instructions and tests directly in chat; repository edits and state-changing commands require explicit delegation. This Architecture chat is authorized to update the planning documents on request.
- One module per chat and one active task at a time. Every required task test must pass on applied code before advancement. The user opens the next module chat after its predecessor's task/module gates pass.
- Explain what and why, data flow, tradeoffs and defense concepts. Present every file as ordered logical code sections, explaining each section before its code and key behavior afterward. Do not provide unexplained whole-file blocks. Supply the complete current-task guide when practical; section-by-section teaching does not mean arbitrary tiny delivery rounds.
- Carry over the IRM manual-guide conventions, while applying these newer VisionQ preferences. See WORKFLOW for the inspected chats and access limits.

## Current filesystem and completed work

Workspace: `/Users/morshedalam/Developer/AI/visionq`.

At initial inspection it contained only `docs/Thesis Proposal.docx` and incidental `.DS_Store`; it was **not a Git repository**. The original proposal contains three candidate topics and has been preserved unchanged. Topic 3 was selected by the user. The attached pasted text lists six papers; their citations/findings are retained in the research document, so future chats need not depend on the temporary attachment path.

On the later workflow-update inspection, Git was present on branch `main`, latest commit `1f66779` (`Initial commit`), with a clean working tree before this documentation update. Retain the existing repository; do not initialize/reset it again. No application source or configuration was observed. The Git change is an observed prerequisite, not a passed M1.T1 gate.

Completed in this planning session:

- Read the topic/proposal, audited the supervisor repository and reviewed relevant full-paper sections from all six supplied papers.
- Reviewed two additional LLM grounding/citation papers and current official implementation documentation.
- Created the documentation index, dataset specification, architecture, stack, module/task plan and evaluation/thesis plan.
- Recorded design assumptions, unanswered hardware/institutional questions and November deadlines.
- Independent final review: **PASS after two rounds** on 21 October 2026. Four contract findings were corrected and rechecked; see the [review record](../review/review-log.md). This is a documentation-quality pass only.
- Added the user-led, section-by-section teaching workflow, task evidence register and module-chat kickoff; adjusted the schedule to sequential module delivery and recorded the UI history/performance requirement.

**Not done:** source scaffolding, installed/locked project dependencies, dataset download/audit, training, inference, database migrations, Docker deployment, local model benchmarking, agent/MCP/RAG implementation, experiments, report writing, slides or submission. There are no measured project metrics. All M1–M6 task gates are `not_started`; detailed statuses/evidence live in TASK_LOG. No task implementation guide or application test result has been supplied in this workflow-update session.

Current chat role: **Architecture agent**, chat `01a15e88-a95b-7201-b7a1-0c74801ac768`, currently titled **Plan industrial defect detection**. Active implementation module/chat: **none**. User opens the M1 chat when ready; this chat does not start M1 automatically.

## Read before changing code

1. [Documentation index](../README.md).
   Also read [guided workflow](WORKFLOW.md) and [task gates](TASK_LOG.md) before proposing code.
2. [Topic and literature](../research/topic-and-literature.md) and [dataset contract](../research/dataset-specification.md).
3. [Architecture](../design/architecture.md) and [technology stack](../design/technology-stack.md).
4. [Development plan](../plan/development-plan.md) and [evaluation protocol](../plan/evaluation-and-thesis.md).
5. [Review record](../review/review-log.md).

## Decisions to preserve

| Decision | Reason |
|---|---|
| Supervised NEU-DET + YOLO11n | Source labels match known-class box detection; supervisor repo is a literature index, not runnable code |
| Main LLM study compares RAG-only, SQL+RAG, and verification | Establishes an empirical contribution beyond adding a chat interface |
| Local Ollama, candidate Qwen3 4B Instruct and EmbeddingGemma | Small provisional models; actual local feasibility must be measured |
| PostgreSQL/pgvector plus local immutable artifacts | Keeps storage/retrieval compact and preserves lineage |
| One Python codebase, FastAPI, Streamlit, CLI worker, MCP server | Bounded implementation for a one-student deadline |
| Five read-only typed MCP tools | Auditable metric/retrieval access without arbitrary SQL or autonomous writes |
| API-owned immutable question snapshots and evidence | MCP stays read-only; quality, run and corpus evidence cannot change between tool calls |
| 12 dev + 48 frozen test questions | Feasible, leakage-aware LLM study with coverage/abstention and fair verification ablation |
| No production yield/causal/trend claims | NEU lacks established normal controls and real factory metadata |
| User-led explained sections and strict task gates | The user needs to understand and implement the thesis, with passing evidence before each next task |
| History and performance UI | Browse/reopen past runs and AI answers, compare labeled-data precision/recall/mAP; confidence is not accuracy |

Review corrections to preserve during implementation: inference results must be scoped to explicit dataset/model/batch/run membership; comparisons require one inference-run ID per side. B1/B2 must render unchecked draft values with no hidden canonical correction. All detector correction choices happen before held-out test evaluation. See the architecture and review record for the full contracts.

## Immediate next work

**Next action:** the user opens one M1 module chat using the kickoff in WORKFLOW. In that chat, begin **M1.T1** with a read-only baseline inspection and a guided manual implementation packet. Retain existing Git, explain the project skeleton and hardware checks, and provide code in explained file sections plus commands for the user. Confirm the exact submission date/report format when available. Do not install or modify application files automatically.

After every required M1.T1 check passes, guide M1.T2, then M1.T3 in that same chat, each with its own evidence gate: a tiny persisted fixture, Docker services and real local LLM/embedding/MCP feasibility test. Record CPU/RAM/GPU, Docker resources, generator latency/RAM, model digests and tool round-trip success. Resolve this early; macOS Docker does not provide Apple GPU acceleration to standard Ollama containers. Use a smaller local model or available Linux GPU if necessary, not an unannounced hosted model.

After the M1 module gate, proceed sequentially through separate M2, M3, M4, M5 and M6 chats. Capture methodology, learning and report notes inside each active task; assemble the report in M6. Do not open parallel implementation modules. In M4, build real history/performance views and the defined agent/evidence view structure; connect the live agent in M5.T1. Do not present fixture content as live AI results.

## Open decisions and risks

| Item | State and action |
|---|---|
| Exact November submission date and report format | Unknown; obtain from user/university when available; move dates earlier if required |
| GPU, RAM and available weekly hours | Unknown; inspect/ask during M1; original estimate is 146–184 focused hours, now requiring recalibration for learning/manual application/test cycles |
| Supervisor acceptance of expanded LLM contribution/title | Not confirmed; prepare the research questions and comparison for discussion |
| Dataset archive/rights/XML indexing/partitions | Not inspected; resolve in M2 before release, never assume downloaded facts |
| Runtime/library/model pins | Candidates selected, no lock tested; resolve in M1 and freeze before experiments |
| Independent human benchmark grader | Not arranged; seek peer/supervisor grading and disclose if unavailable |

## Session update protocol

Before work, identify the task ID, learning outcomes and required checks. In module chats, supply exact amendments to this file and TASK_LOG directly in chat for the user to apply; save them yourself only when explicitly asked. Record observed versus supplied versus applied code, actual test evidence, new decisions and the exact next step. Only mark `passed` when all required checks pass. Keep original source material unchanged and never claim a proposed handoff update has been saved.

Use this compact log format for future entries:

```text
Date:
Task IDs and status:
Changes and artifact paths:
Supplied and applied section/change IDs:
Checks actually run and results:
Required checks still missing or failing:
What the user learned and report/defense notes:
Experiment IDs / config hashes / model digests:
Decisions or deviations:
Unresolved items:
Next task and first action:
```

No build/test commands are listed as working yet. The future CLI should expose ingest, validate, release, train, infer, index-docs, evaluate and reconcile commands, but implement and verify them before documenting executable usage.

## Suggested prompt for the next chat

Use the full [module kickoff in WORKFLOW](WORKFLOW.md). For M1: ask Codex to act as the Module 1 guide, inspect read-only, explain what/why and supply each file in ordered explained code sections for M1.T1. The user applies the code and runs required tests. Stay on M1.T1 until all required checks pass; then guide the next task in the same chat. Preserve local Docker AI, the major LLM contribution, required MCP/RAG and the November deadline. Provide evidence-based handoff updates for manual application.
