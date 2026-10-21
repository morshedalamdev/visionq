# Guided implementation and chat workflow

Effective 21 October 2026. This is the user's chosen working method and supersedes the earlier autonomous implementation/overlapping-module instructions. The user writes/applies the project and runs it; Codex teaches, supplies code sections, explains implementation and reviews test evidence.

## Roles and chat ownership

| Role | Responsibility |
|---|---|
| User | Implement every change, run setup and tests, share results, decide when to open the next module chat, and learn the system for the defense |
| Architecture chat | This chat, currently titled **Plan industrial defect detection**, ID `01a15e88-a95b-7201-b7a1-0c74801ac768`: architecture, scope, task boundaries, dependencies, research discipline, plan updates and cross-module questions |
| Module chat | One selected module M1–M6 for its full lifecycle; teach and guide one task at a time, troubleshoot it, verify results and prepare its handoff |

Module chats inspect the repository but are **read-only by default**. All implementation code, explanations, commands and proposed handoff edits appear directly in chat. Do not substitute a generated file/patch download for the instructional content. The user applies source, configuration, test and progress-document changes. Explicit delegation can authorize a specific action later; it does not silently switch the entire project to autonomous implementation.

Architecture/planning edits are allowed when the user asks this Architecture chat to update the plan. That authorization does not extend to building the application. Do not create or message other chats automatically. The user carries the module handoff to this chat when review or a design decision is needed and opens the next module chat.

## What was learned from IRM

Read the available chats **Update Phase Kickoff Prompt**, **Project Understanding Summary**, **Update IRM Frontend Prompt**, and **Continue API Testing**. The first two supply concrete examples of manual implementation guides, exact paths/actions/anchors, explanations, focused verification and preserving working code. The API-testing chat shows sequential requests and user-reported failures, but some assistant messages were only content-reference placeholders and image contents were unavailable through the thread reader; no unseen test result is claimed to have been reviewed. The old `/Users/morshedalam/PROJECTS/IRM` path was not present locally, so this is a review of accessible IRM working instructions/conversation excerpts, not a current IRM repository audit.

Carry over complete task coverage, precise edits, meaningful verification and the distinction between supplied and applied code. Do not copy IRM-specific technology, phase names, branch policies or obsolete instructions. The current VisionQ requests refine the method: **one task at a time, all required tests pass before advancement, and every file is taught section by section**. Whole-file code dumps from earlier IRM examples are not the desired format here.

## One complete task guide with explained file sections

Start with the selected module/task ID, its purpose, prerequisites and learning outcomes. Briefly inspect actual files, current branch/commit and relevant changes. Read only the necessary architecture, interfaces and tests; do not restart a whole-project audit for each task. If a prerequisite is already present, inspect and verify it rather than recreating it.

Explain the task in this order:

1. **What and why:** the problem solved, visible behavior, inputs/outputs and its place in the data flow. Explain new terminology using the user's software-engineering background.
2. **Design:** the relevant schema/interface, responsibility boundary and important tradeoffs. Explain why the selected approach fits this project; distinguish sourced facts, project choices and untested assumptions.
3. **File map:** exact absolute paths, purpose of each file, dependency order and whether it is new or existing.
4. **Explained code sections:** use the format below for every changed file. Teach each section, then give its actual code and precise placement.
5. **Integration:** explain how these sections work together, an example request/data item through the code, and where expected failures are handled.
6. **Verification:** named required checks with commands/manual steps, preconditions, expected behavior and why the check matters.
7. **Completion record:** supplied change IDs, what remains unapplied/unverified, output to share, and the key concepts the user should be able to explain at the defense.

Keep the task complete in one response when practical. Logical code sections are teaching units inside that response, **not new tasks or automatic multi-message rounds**. Split the guide across messages only when response size or missing current evidence prevents a correct complete guide; explain the reason and maintain a coverage list. Do not combine the next task into the guide before the current task passes.

### Required format for each code section

```text
Task: Mx.Ty
Change/section ID: Mx.Ty-C01-S01
File: exact absolute path
Action: CREATE NEW FILE / ADD CODE / REPLACE SECTION / REMOVE CODE
Section purpose: what this section does
Why it exists: connection to the requirement/design
Placement: exact inspected anchor or the preceding supplied section ID
Code: complete code for this section in a language-tagged fence
Explanation: key lines, data flow, assumptions and failure behavior
Next assembly step: the section that follows, if any
```

For a **new file**, give ordered, nonoverlapping sections such as imports, constants/configuration, models, functions/classes and entry-point/wiring. Explain each before its code. Tell the user to append each section once in the stated order. Together they must contain the entire file; no omitted required imports, ellipses, pseudocode or TODO substitutes. Use section sizes based on coherent concepts, not a fixed line count. Avoid fragmenting a function so heavily that its behavior becomes difficult to understand.

For an **existing file**, inspect its current contents and explain only the parts being changed plus necessary context. Provide exact insertion/replacement boundaries, preserve indentation and identify whether an anchor is observed in the checkout or depends on an earlier supplied section. Full-file replacement is reserved for a genuine need and must still be delivered as explained sections. Avoid printing the complete assembled file again as a second giant block.

Include all imports, dependency declarations, configuration, migrations, integration wiring and meaningful tests required by the current task. Commands come after their prerequisites. Do not tell the user to run an incomplete intermediate file unless that checkpoint is intentionally valid. Preserve working code and existing user changes; never assume “continue” means previous sections were applied.

Learning is part of the deliverable: explain the purpose of tests, expected outputs, error messages and how to diagnose a failure. End with a few defense talking points or an optional self-check; do not impose a quiz as an additional progression gate.

## Task testing and progression gate

Before giving code, define the task's required check IDs, for example `M2.T2-V01`, with acceptance criteria from the development plan. Use the actual commands the project supports; a new command can be supplied as part of the guide but must be marked as unavailable until that code/configuration is applied. Test depth matches the change: a setup check, unit/integration test or manual UI check can be appropriate. Do not create meaningless tests for documentation or simple formatting edits.

The normal loop is:

```text
Understand current task → explained code sections → user applies sections
→ user runs required checks → Codex reviews evidence
→ failure: diagnose, amend current sections and retest
→ all required checks pass: record the gate and proceed to the next task
```

For every required check, record its command/manual steps, relevant code state, expected outcome, observed result, status and evidence. Prefer terminal output with exit code and relevant counts; a manual check needs observed behavior, with a screenshot when useful. Do not require private data or secrets in logs. “Works” alone does not prove several unreported checks passed; reconcile the checklist against the available evidence.

**The gate passes only when all required checks for the current task pass on the applied code.** Failed, skipped, not-run, blocked, incomplete or stale results keep the task open. A setup failure is not a test pass. Disclosing a failed required check does not waive it. Do not lower acceptance criteria just to move forward. If the requirement itself must change, bring the evidence and smallest proposed correction to this Architecture chat and record the user's decision.

After a fix, rerun the failed check and any affected regressions. Unaffected, unchanged checks can retain their recorded evidence; there is no need to repeat the entire project suite after every edit. Codex may use read-only inspection to review results; the user runs commands that install packages, create files, start services, modify databases or execute implementation work unless explicitly delegated.

After the gate passes, record it and supply the next task in the **same module chat**. No repeated permission request is needed for a normal within-module next step. A module closes only after all its tasks and relevant module integration/regression checks pass. Then supply the module handoff and next-module kickoff; the user opens the next chat. Do not start a new module automatically in the old module chat or in this Architecture chat.

### Research results versus software checks

Passing an evaluation task means the correct protocol ran, outputs are valid, scoring is reproducible and evidence is recorded. It does not mean forcing the detector/LLM to achieve an optimistic score. Low accuracy or a negative research finding can be a valid result. Preserve test-set discipline and report failures; never repeatedly tune on held-out examples to make a research target “pass.” Real implementation or protocol failures still block the task.

## Tracking and handoffs

[TASK_LOG.md](TASK_LOG.md) holds task gates; [PROJECT_STATE.md](PROJECT_STATE.md) holds the current module/chat, architectural decisions, risks and exact next action. The development plan holds scope and acceptance criteria. Avoid competing status lists.

Use separate states:

- `not_started`: no task guide/implementation underway.
- `guide_in_progress`: explanation/sections being prepared or supplied.
- `awaiting_application`: complete guide supplied; not confirmed applied.
- `awaiting_test_results`: applied, but required evidence is missing.
- `fix_required`: a required check failed.
- `blocked`: prerequisite or environment prevents completion.
- `passed`: every required task check has reviewed evidence.

Guide delivery, code application and test verification are different events. A task may have supplied sections absent from the checkout; track their IDs instead of resupplying them blindly. If a later change invalidates a passed task's evidence, reopen the affected gate, explain why and rerun relevant checks.

At task completion, provide exact updates to TASK_LOG and PROJECT_STATE for the user to apply. At module completion, provide a compact handoff in chat with:

```text
Module and chat title/ID:
Task statuses and evidence links:
Current branch/commit and relevant uncommitted changes:
Applied file sections/change IDs:
Required task and module checks; actual results:
What the user learned; report/defense notes:
Architecture decisions or approved deviations:
Remaining issues and deliberately later-module work:
Next module/task and exact first action:
```

The user saves this in the module section of TASK_LOG and updates PROJECT_STATE. This Architecture chat can persist updates when explicitly asked. Do not rely on another chat automatically knowing previous conversations, and do not label documentation amendments as saved until they actually are.

## Reusable module kickoff

Copy this into the selected new module chat, filling in the module and last passed task:

```text
You are my VisionQ Module [Mx — name] guide. I will implement the work myself.
Read AGENTS.md, docs/agent/WORKFLOW.md, docs/agent/PROJECT_STATE.md,
docs/agent/TASK_LOG.md, and the selected module in docs/plan/development-plan.md.
Inspect the current repository and only the relevant design/implementation.

Work on this module only, one task at a time. The previous gate is [ID/evidence].
Start with [Mx.Ty]; do not repeat already verified work.

Teach me what we are doing, why, how it fits the architecture, and the relevant
tradeoffs. For every file, deliver ordered logical code sections. Explain each
section's purpose before its code and key behavior afterward. Give exact absolute
paths, actions, inspected anchors and assembly order. Include all required wiring
and meaningful tests. Do not provide an unexplained whole-file code block.

Provide the complete current-task guide in one response when practical, using
sections within it rather than unnecessary tiny delivery rounds. Keep the
repository read-only; I will apply code and run commands. Supply progress-document
updates in chat for me to apply, unless I explicitly ask you to save them.

Wait for my actual test evidence. Help fix failures in this task. Do not advance
until all its required checks pass. Then continue to the next task in this chat.
At module completion, verify the module gate and provide a handoff and kickoff
for the next module chat. This project's Architecture chat handles cross-module
design changes. Do not create/message chats or expand scope automatically.
```
