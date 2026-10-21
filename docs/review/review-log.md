# Independent planning review

Review target: the documentation package created on 21 October 2026. This reviews research coverage, architecture, feasibility and consistency; it does not certify unbuilt software or unrun experiments.

Status: **PASS after two independent review rounds**, 21 October 2026.

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
