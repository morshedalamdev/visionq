# VisionQ agent handoff and project state

Last updated: 21 October 2026, Asia/Shanghai. This is the canonical continuation record. Read it before implementing in a new chat; check the filesystem rather than assuming this snapshot is still current.

## User intent and binding requirements

- Final-year thesis with December graduation/defense; **project and report must be completed during November 2026**. Working deadline 30 November, submission-ready target 25 November; exact institutional date is not known.
- Original topic: A Data Engineering Framework for Industrial Visual Defect Detection Using Machine Learning.
- Combine data engineering, software engineering and a **major LLM research contribution**. LLM work is not an optional reporting extra.
- Run the AI locally in Docker. No hosted LLM, paid API or cloud spending has been requested.
- MCP/RAG should be included when they fit, not inserted just for terminology and not left as optional if useful. Current design includes document RAG and a small five-tool MCP server as required components.
- A general agent platform may be built only if needed. Current requirements are met by a single bounded agent; no need has been identified for a general platform.
- The user requested a documentation plan first, followed by independent subagent challenge/review and correction until passed. Do not confuse that planning review with implementation validation.

## Current filesystem and completed work

Workspace: `/Users/morshedalam/Developer/AI/visionq`.

At initial inspection it contained only `docs/Thesis Proposal.docx` and incidental `.DS_Store`; it was **not a Git repository**. The original proposal contains three candidate topics and has been preserved unchanged. Topic 3 was selected by the user. The attached pasted text lists six papers; their citations/findings are retained in the research document, so future chats need not depend on the temporary attachment path.

Completed in this planning session:

- Read the topic/proposal, audited the supervisor repository and reviewed relevant full-paper sections from all six supplied papers.
- Reviewed two additional LLM grounding/citation papers and current official implementation documentation.
- Created the documentation index, dataset specification, architecture, stack, module/task plan and evaluation/thesis plan.
- Recorded design assumptions, unanswered hardware/institutional questions and November deadlines.
- Independent final review: **PASS after two rounds** on 21 October 2026. Four contract findings were corrected and rechecked; see the [review record](../review/review-log.md). This is a documentation-quality pass only.

**Not done:** Git initialization, source scaffolding, installed/locked project dependencies, dataset download/audit, training, inference, database migrations, Docker deployment, local model benchmarking, agent/MCP/RAG implementation, experiments, report writing, slides or submission. There are no measured project metrics. All M1–M6 implementation tasks are `not_started`.

## Read before changing code

1. [Documentation index](../README.md).
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

Review corrections to preserve during implementation: inference results must be scoped to explicit dataset/model/batch/run membership; comparisons require one inference-run ID per side. B1/B2 must render unchecked draft values with no hidden canonical correction. All detector correction choices happen before held-out test evaluation. See the architecture and review record for the full contracts.

## Immediate next work

**Next task: M1.T1.** Inspect current files and any new user instructions; initialize the agreed project skeleton/Git and collect hardware facts without installing a large stack prematurely. Confirm exact submission date/required report format when available. The planning assumptions permit work to proceed without that answer.

Then complete M1.T2 and M1.T3: a tiny persisted fixture, Docker services and real local LLM/embedding/MCP feasibility test. Record CPU/RAM/GPU, Docker resources, generator latency/RAM, model digests and tool round-trip success. Resolve this early; macOS Docker does not provide Apple GPU acceleration to standard Ollama containers. Use a smaller local model or available Linux GPU if necessary, not an unannounced hosted model.

After M1, follow M2 data release and M3 detection while beginning M4 tools/retrieval and M5 benchmark design on fixtures. M6 report writing runs throughout. Do not wait until the detector is perfect to start the LLM work or the report.

## Open decisions and risks

| Item | State and action |
|---|---|
| Exact November submission date and report format | Unknown; obtain from user/university when available; move dates earlier if required |
| GPU, RAM and available weekly hours | Unknown; inspect/ask during M1; estimate is 146–184 focused hours |
| Supervisor acceptance of expanded LLM contribution/title | Not confirmed; prepare the research questions and comparison for discussion |
| Dataset archive/rights/XML indexing/partitions | Not inspected; resolve in M2 before release, never assume downloaded facts |
| Runtime/library/model pins | Candidates selected, no lock tested; resolve in M1 and freeze before experiments |
| Independent human benchmark grader | Not arranged; seek peer/supervisor grading and disclose if unavailable |

## Session update protocol

Before work, identify the task ID and its acceptance criteria. After work, update this file and the development plan's task status if tracked there. Record changed files, actual commands/checks, pass/fail results, new decisions, unfinished work and the exact next step. Cite artifact paths or run IDs; never mark something complete because it was merely planned or generated. Keep the original proposal and source data unchanged.

Use this compact log format for future entries:

```text
Date:
Task IDs and status:
Changes and artifact paths:
Checks actually run and results:
Experiment IDs / config hashes / model digests:
Decisions or deviations:
Unresolved items:
Next task and first action:
```

No build/test commands are listed as working yet. The future CLI should expose ingest, validate, release, train, infer, index-docs, evaluate and reconcile commands, but implement and verify them before documenting executable usage.

## Suggested prompt for the next chat

> Continue VisionQ from docs/agent/PROJECT_STATE.md. Read the linked architecture, development plan, evaluation protocol and review record. Check the current workspace, then implement the next incomplete task starting with M1.T1. Preserve local Docker AI, the major LLM contribution, required MCP/RAG, the November project/report deadline and honest task status. Update the handoff with evidence before finishing.
