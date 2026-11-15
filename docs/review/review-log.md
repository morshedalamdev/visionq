# Independent planning review

Review target: the documentation package created on 21 October 2026. This reviews research coverage, architecture, feasibility and consistency; it does not certify unbuilt software or unrun experiments.

Original architecture/planning review: **PASS after two independent review rounds**, 21 October 2026. Later workflow amendments are tracked separately below; the original pass does not certify new software or tests.

Research was parallelized across separate agents for the engineering papers, vision repository/papers, and LLM design. After the draft package was complete, a separate agent (`final_reviewer`) read the documents and challenged the contracts. Findings and corrections are recorded below; a pass is recorded only after the reviewer actually issues it.

## Review criteria

- User requirements are reflected: November project/report completion, major LLM contribution, local Docker AI, justified MCP/RAG, appropriate agent scope.
- Repository and all six supervisor papers were inspected with honest access limits and primary citations.
- Dataset/annotation/split assumptions are explicit; anomaly detection is not confused with supervised detection.
- Architecture has coherent interfaces, storage, provenance, retry semantics, model evaluation, RAG and agent evidence handling.
- Six-module plan is balanced, ordered, testable and schedulable, with report writing and final submission preparation included.
- LLM baselines, controlled ablation, gold evidence, leakage prevention and anti-abstention metrics are credible.
- Stack and handoff distinguish decisions from installed/implemented facts.
- Relative documentation links work, original proposal is retained, and review findings are resolved or honestly scoped.

## Review rounds

### Round 1 on 21 October 2026

Verdict: **REVISE**. The reviewer found four actionable contract gaps and one improvement; no scope redesign was required.

| Finding | Correction applied | Recheck location |
|---|---|---|
| Read-only MCP appeared to persist evidence; multiple calls could read changing states | API owns repeatable-read analytical snapshot capture, evidence/answer persistence and idempotent request audit. MCP only selects from that snapshot and pinned corpus. Persistence failure produces an error. | Architecture: Question snapshot and persistence ownership; flow and Compose table |
| Run/result membership and repeated-run comparisons were underspecified | Explicit inference dataset/model/batch FKs, immutable membership, composite result membership constraints and left/right inference-run IDs; shared-asset/version fixture added | Architecture: Storage contract and MCP tool table |
| Canonical numeric rendering could accidentally validate the unverified baselines | Shared draft fields preserve claimed values; B1/B2 render unchecked values, B1 has no hidden SQL lookup; only P checks/repairs/canonicalizes | Architecture: answer schema; evaluation: controlled ablation |
| Weak detector accuracy correction appeared after test evaluation | Any bounded correction is decided from train/validation and completed before test; post-test fixes retain original results and need a deviation/fresh confirmation or exploratory label | Development plan: M3 gate |
| Metric names/formulas could diverge across implementations | Added canonical metric catalogue, units, zero-denominator and comparison rules | Architecture: Metric catalogue |

The reviewer independently verified current primary MCP documentation and named local model candidates, confirmed coverage of the six supplied papers, and found the overall scope and schedule coherent. This is not supervisor approval or confirmation of hardware feasibility.

Root structural checks: all local Markdown links resolve; fenced blocks are balanced; six modules contain 22 unique task IDs; no application files were introduced; the original proposal remains present and was not edited. SHA-256 of the retained proposal: `e8cc2cb483b061e35ef693ca6611f2606fe63b6d166cb7599068c04e12476ac9`.

### Round 2 on 21 October 2026

Verdict: **PASS**. The reviewer re-read the corrected architecture, evaluation protocol, development plan, handoff and review record. All four findings were resolved coherently; the metric catalogue and associated challenge cases introduced no blocking inconsistency.

Final reviewer statement: “No blocking documentation issue remains. This approves the plan's coherence, not implementation performance or supervisor acceptance.”

Hardware feasibility, the exact institutional deadline, the actual dataset archive/rights, dependency/model compatibility and supervisor acceptance remain explicit M1/M2 checks. They are unknown implementation inputs, not completed checks. The root repeated the structural validation after corrections: all 10 Markdown files (including root AGENTS.md) passed local-link/fence checks, with six modules and 22 unique tasks. No software tests or research experiments were run because this deliverable is documentation only.

## User-led workflow amendment on 21 October 2026

The user will implement the project themselves, with this chat acting as Architecture agent and one separate chat per module. Each task must pass all required checks before advancement. Later clarification requires teaching what/why and every file in explained logical sections, not whole-file code dumps.

An independent read-only consistency review identified overlapping module dates, autonomous implementation instructions, a UI dependency on the not-yet-built agent, and wording that could waive required checks. The amendment replaces these with sequential M1–M6 dates, a strict evidence gate, read-only module guidance, M4 fixture UI/M5 live-agent integration, and an explicit distinction between research outcomes and software checks. The benchmark freeze moves to 14 November, with experiments on 15–18 November; November completion remains the goal.

Added WORKFLOW.md and TASK_LOG.md, updated root AGENTS.md and PROJECT_STATE, and aligned the development/evaluation plans and index. Also made the previously discussed history/performance UI explicit. Read-only inspection found existing Git (`main`, commit `1f66779`); the state record was corrected without claiming M1.T1 passed. Review evidence comes from accessible IRM chats, not an unavailable local IRM repository.

Amendment validation: **PASS**, independently rechecked by `workflow_consistency` against the actual revised files. Teaching/section assembly, manual application/testing, strict task gates, sequential dates, the November 14 freeze, M4/M5 UI integration and handoff records are consistent. Applied its final wording suggestion so root AGENTS identifies the designated Architecture chat without assigning that role to every module chat.

Structural validation passed for all 12 Markdown files: no broken local links or unmatched fences, six modules with 22 unique task IDs matching TASK_LOG. `git diff --check` passed. No source implementation, dependency installation or application test was performed, and no task gate was marked passed.

## Azure and twelve-month usage amendment on 13 November 2026

User request: use the newly activated Azure student subscription and relevant GitHub Student Pack services, with a twelve-month usage horizon. The user subsequently reconfirmed project/report completion by November 30, December rehearsal and a defense around December's second week. Full-time priority was expressed; exact daily capacity and university dates remain unknown.

Evidence: read-only Brave inspection showed $100/$100 credit, expiry November 13, 2027 and $0 November cost. No quotas, prices or GitHub account entitlements were verified. Two research agents (`azure_research`, `student_pack_research`) checked current primary documentation; their findings inform the source-linked [Azure/student-services plan](../design/azure-and-student-services.md).

Design change: one on-demand Azure VM running the existing Docker stack, private Blob backups and a verified local fallback. At the time of this November 13 review, Ollama was the selected self-hosted server; core SQL/RAG/MCP/verifier and research comparisons remain intact. GitHub repository/Actions are selected support, with other Pack offers gated by an actual need. The $100 is allocated over the whole year; post-defense idle compute/disk cleanup follows verified recovery. No resources or accounts were changed.

Rebased the elapsed calendar to a conditional November 13–30 sequence, preserving six modules/22 tasks and every required gate. Added Azure checks inside existing tasks, kept the section-by-section/manual implementation workflow, and separated December rehearsal and later maintenance from thesis completion. The original estimate plus bounded cloud additions is 152–196 focused hours before unmeasured learning/retry time; this is explicitly a high-risk forecast with no dependable buffer.

Independent amendment review, round 1: **REVISE** from `azure_plan_review`. It identified two narrow gaps: an ARM laptop and x86 VM cannot be assumed to share a platform image digest, and model-term checks must precede M1 downloads rather than wait for the M2 dataset audit. Corrected the Azure plan, architecture, stack, M1 task gates and evaluation wording: record/test platform-specific images from the same source/release, keep final B1/B2/P on one fixed host/image profile, and check model terms in M1 before downloads while dataset rights remain in M2 before acquisition/cloud upload.

Round 2: **PASS**. The same independent reviewer re-read the corrected files and verified both findings resolved. It confirmed that the year-long credit allocation, post-defense cleanup, November 30 deadline and mandatory task gates remain consistent. This approves documentation coherence only; deployment feasibility, runtime performance and implementation completion remain unverified.

Initial structural checks passed: 13 Markdown files, valid local links and balanced fences; six modules with 22 unique tasks matching TASK_LOG; all task statuses still `not_started`; `git diff --check` passed. The original proposal SHA-256 remains `e8cc2cb483b061e35ef693ca6611f2606fe63b6d166cb7599068c04e12476ac9`. The pre-existing `.DS_Store` change was left untouched. No application tests, provisioning or experiments were run.

## vLLM runtime decision — 15 November 2026

The user selected vLLM in place of Ollama. This supersedes the serving choice recorded above. The active design now has separate private chat and embedding endpoints, revision-pinned native snapshots and a new two-service feasibility check inside M1.T3. The current Azure budget, local offline restart, research comparisons and manual task gates remain binding. No model was downloaded, cloud resource provisioned or application test run for this amendment.

Independent review by `vllm_plan_review`: **PASS**. The reviewer checked the architecture, stack, Azure plan, evaluation protocol and handoff against the M1.T3 checks. This was a documentation review; hardware fit, response times and credit use remain unmeasured. All 13 Markdown files passed local link/fence checks; the six modules and 22 unadvanced task gates still match.
