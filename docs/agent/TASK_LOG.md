# Task gates and module handoffs

Updated **15 November 2026**. This file tracks **verified implementation**, not planning quality. Apply the [workflow](WORKFLOW.md). No implementation task has passed; Git and Azure credit exist, but neither completes M1.T1. Azure requirements are included in the existing task gates; see the [deployment plan](../design/azure-and-student-services.md).

Current role: Architecture chat. Active implementation module/chat: none. Next selected task when the user opens the M1 chat: **M1.T1**. No task code guide has been supplied or applied in this session, and no application test evidence has been reviewed.

## Task register

| Task | Status | Required-check evidence | Notes |
|---|---|---|---|
| M1.T1 | not_started | None | Retain Git; Azure credit observed only; quota/price/hardware/GitHub preflight pending |
| M1.T2 | not_started | None | Compose, persistence, private Blob fixture adapter and CI pending |
| M1.T3 | not_started | None | Both vLLM services, five timed Azure questions with MCP/retrieval, local offline restart, isolation/deallocation pending |
| M2.T1 | not_started | None | |
| M2.T2 | not_started | None | |
| M2.T3 | not_started | None | |
| M2.T4 | not_started | None | |
| M3.T1 | not_started | None | |
| M3.T2 | not_started | None | |
| M3.T3 | not_started | None | |
| M4.T1 | not_started | None | |
| M4.T2 | not_started | None | |
| M4.T3 | not_started | None | |
| M4.T4 | not_started | None | |
| M5.T1 | not_started | None | |
| M5.T2 | not_started | None | |
| M5.T3 | not_started | None | |
| M5.T4 | not_started | None | |
| M6.T1 | not_started | None | |
| M6.T2 | not_started | None | |
| M6.T3 | not_started | None | |
| M6.T4 | not_started | None | |

## Per-task evidence template

Create an entry when a task begins. Commands below are placeholders for actual inspected/supplied commands, not runnable instructions.

```text
Task and module chat:
Status:
Learning outcomes and purpose:
Code baseline (commit + relevant diff/hash):
Supplied section/change IDs:
Applied section/change IDs:

Required checks:
  Check ID:
  Purpose and acceptance criterion:
  Exact command / manual UI steps and working directory:
  Expected result:
  Actual result / exit code:
  Evidence location or pasted-output reference:
  Status (PASS / FAIL / NOT_RUN / BLOCKED):
  Reviewed by and date:

Fix attempts and affected regression checks:
Gate decision (all required checks PASS? yes/no):
What the user learned; report/defense notes:
Unresolved issues:
Exact next action:
```

For manual checks, record observable behavior, not only a checkbox. For a research experiment, store the actual score/result separately from whether the evaluation protocol passed its checks.

For cloud-related checks, also record redacted resource configuration, region/SKU, price source/date, cumulative credit use, remaining balance, private-access evidence and final resource power state. Do not paste secrets or treat an alert/budget as an enforced spending stop. Catalogue benefits are not account activation evidence.

## Planning-only update on 13 November

Observed Azure Education overview: $100 available, expiry November 13, 2027, November cost $0. User confirmed November 30 project/report completion, December rehearsal and approximate second-week defense. Added a separate twelve-month Azure usage plan and integrated its checks into the existing 22 tasks. No resources provisioned, benefits activated, application tests run or task statuses advanced. Documentation review results belong in [review-log](../review/review-log.md), not task gate evidence.

On **15 November**, the model server was changed in the plan to vLLM. Implementation evidence must satisfy the four [M1.T3 checks](../plan/development-plan.md); no check was executed or credited by this planning change.

## Module completion register

| Module | Module chat | All task gates | Integration/regression gate | Handoff |
|---|---|---|---|---|
| M1 | Not opened | Pending | Not run | Not supplied |
| M2 | Not opened | Pending | Not run | Not supplied |
| M3 | Not opened | Pending | Not run | Not supplied |
| M4 | Not opened | Pending | Not run | Not supplied |
| M5 | Not opened | Pending | Not run | Not supplied |
| M6 | Not opened | Pending | Not run | Not supplied |

Add each completed module's handoff here using the workflow template. Do not overwrite earlier failed attempts or label unapplied guide content as implemented.
