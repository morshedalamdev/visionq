# Evaluation protocol and thesis deliverables

All experiments below are planned. No scores, trained model or latency measurements exist yet. Freeze the relevant inputs and protocol before each final experiment. Follow the user-led [workflow](../agent/WORKFLOW.md): Codex explains the purpose/code/checks, the user implements and executes them, and all required task checks must pass before advancement. Keep research outcomes separate from software acceptance checks: an honest negative result can answer a research question.

## Experiment A Data pipeline reliability

Compare a documented minimal baseline import script with the proposed framework on the same small fixture collection and the same real archive. The baseline decodes images and imports labels but lacks the framework's explicit rule reporting, manifest lineage and resumable state. Specify its behavior in advance; do not deliberately sabotage it.

Create a clean reference fixture plus labeled fault variants covering every DQ01–DQ10 case, exact duplicates, conflicting labels, missing labels and a worker interruption. Keep fault fixtures separate from the model's evaluation dataset. For each injected case, record the expected outcome and the observed result. Also run clean inputs to measure false quarantine. Distribution-change warnings count as warnings, not corrupt-file detections.

Measure fault detection by rule (caught/introduced), false-quarantine rate on valid fixtures, invalid records reaching a released dataset, duplicate logical rows after rerun, lineage-field completeness, recovery after interruption, ingestion images/second and resource use. Acceptance targets: every enumerated invalid fixture blocked as specified, zero duplicate logical rows on identical rerun, and all successful result rows resolvable to their input/model/config. These are finite test-suite targets, not a guarantee of detecting all future bad data.

Kill the worker after an artifact write and before database commit, and after a per-image result transaction. Resume and reconcile; verify no dangling committed references or double-counted detections. Back up and restore one complete run and compare manifest/checkpoint/evidence hashes.

## Experiment B Defect detection

Use the [dataset split policy](../research/dataset-specification.md). Freeze train/validation/test membership and duplicate groups. Fine-tune one YOLO11n configuration using pretrained weights; keep a short development budget (at most one bounded corrective training configuration after the initial run). Use validation for image size, checkpoint selection, early stopping and the operating confidence threshold. Prefer the validation macro-F1 operating point if no external cost constraint is supplied; record the selection rule before looking at test results.

The released baseline consists of one selected checkpoint. Three seeds are desirable only if the measured training budget permits; decide before final runs, use the same protocol, and report all seeds rather than selecting the best test seed. One seed is acceptable with an explicit uncertainty limitation. Do not run an architecture leaderboard at the expense of the LLM experiment.

Report:

- mAP@0.5 and mAP@0.5:0.95, per-class AP and class support; AP comes from a precision-recall curve, not average precision/recall.
- Precision, recall and F1 at the frozen confidence threshold with stated matching IoU (0.5 for this operating-point report), one-to-one class-aware matching, plus FP/FN counts. Separate this from the evaluator's own automatically selected summary threshold.
- Evaluator version/config, score floor for AP, NMS IoU, maximum detections, image size, split hash and checkpoint hash. A dashboard threshold must not truncate predictions used for AP.
- Inference median and p95 per-image latency at batch size 1, after 10 warmup passes and over at least 100 images where available; state device, precision and whether decode/preprocess/NMS are included. Also report full-pipeline throughput separately.
- Representative false positives, missed boxes and localization/class confusion, especially low contrast and fragmented textures. Include the selection rule for qualitative examples so they are not all favorable.

Do not promise an accuracy score before training. No healthy-image false-positive rate or production yield can be estimated without representative normal data. Do not directly compare our scores to He et al.'s 70/30 split or its accepted manuscript's AP expression. This experiment validates the application data source; it does not prove industrial deployment readiness.

## Experiment C Main LLM study

### Study hypothesis and systems

The hypothesis is that structured metric access plus document retrieval improves correct, supported answers, and that verification reduces unsupported claims with a measurable coverage/latency tradeoff. Local inference, MCP and evidence auditability are implemented properties; they do not by themselves establish improved accuracy.

| Condition | Evidence and behavior | Purpose |
|---|---|---|
| B1 Document RAG | Same local generator; top-k retrieval from approved documentation and bounded textual exports of the frozen metrics; no database tools and no claim verifier | Credible document-based baseline with access to the underlying information |
| B2 SQL tools plus RAG | Same generator, structured metrics through MCP plus document retrieval, no post-generation claim filtering | Measures combined structured/document evidence system |
| P Proposed agent | Same B2 draft/evidence passed through numeric/scope/citation checks; one bounded repair when needed | Main system |

For the controlled verification ablation, save every B2 draft and its evidence and apply the checker to those **exact same drafts**. Report a filter-only result before repair, then the final filter-plus-repair result separately. This isolates verification from differences in retrieval or sampling. Keep original failures in the record. If the verifier only renders approved fields, B2 must render the corresponding unverified fields in the same layout; the difference must not be a more capable UI.

The shared draft schema records claimed metric name/value/unit, numerator/denominator, scope IDs, filters/threshold and cited references. B1/B2 render those model-supplied fields without factual correction; B1 references only retrieved export/document evidence and performs no hidden SQL lookup. P alone validates against the saved canonical evidence and canonicalizes accepted/repaired fields. Schema parsing failures are recorded equally for all arms. Use the [architecture's snapshot ownership and metric catalogue](../design/architecture.md) so tools in one question cannot observe different evolving data states.

B1 receives generated metric exports from the same frozen scopes, not a deliberately empty knowledge base. These exports contain source data, not gold answers or QA phrasing, and are available to all conditions in the same versioned experimental corpus. Record their export/query version and IDs. This is an information-access comparison: B1 must retrieve/interpret prose, while B2/P have structured tools. Do not attribute the entire difference to verification or MCP.

All arms share generator digest, temperature (start at 0), response schema, answer/citation instructions, context/output caps, frozen facts, corpus and question ordering policy. B2/P share tool budget and selection implementation. Equal maximum output does not imply equal compute: report actual model/tool call counts, tokens and latency per arm. Set a reproducible randomized order within each question to reduce cache/order effects, with the same warmup policy.

### Benchmark composition and freeze

Prepare **60 questions total: 12 development and 48 final test**. Development questions use different data snapshots and semantic families from final questions. Keep near-duplicate paraphrases in the same partition. Reusing the same tool intent is allowed; merely changing a class name in an otherwise identical question does not provide strong independence.

| Final test group | Count | Required coverage |
|---|---|---|
| Single-scope numeric facts | 12 | Count, ratio, denominator, zero value, class/run/threshold selection |
| Batch comparisons | 8 | Difference, ordering, tied result, incompatible scope, percentage-point distinction |
| Provenance and data quality | 8 | Model/config version, quarantine count, failed coverage, ruleset |
| Document-grounded interpretation | 8 | Class/metric meaning, dataset limits, preprocessing, model caveats |
| Unsupported or ambiguous premises | 12 | Yield, real time trend, causal machine attribution, physical area/severity, missing ID, unclear model/run |
| **Total** | **48** | Include mixed answerable/unsupported subparts |

Tag each question's expected action (`answer`, `partial`, `clarify`, `abstain`) in advance. The first four groups should principally contain answerable questions; incompatible comparisons are explicitly tagged. Report metrics using the actual tagged answerable/unanswerable denominators, not an assumed 36/12 if the labels differ.

Each benchmark record contains ID, split, family ID, question, scope IDs, expected action, required atomic facts, gold numeric values/tolerances, allowed supporting evidence/chunks, forbidden unsupported claims and scoring notes. Gold values must be audited using independent SQL or hand-checked exports, not only the production metric helper being evaluated. Ideally a peer verifies the reference answers; disclose if that is unavailable.

Prepare the benchmark and rubric during M5, beginning 9 November, after the M4 gate. M5.T1 uses development fixtures; M5.T2 creates the separate formal development/test sets. After the detector is frozen, use immutable test prediction snapshots and finalize gold values without tuning the detector on them. Test question answers and evaluator annotations never enter RAG, prompts or examples. Relevant source documents remain retrievable: evidence access is intended, answer leakage is not.

Freeze by 14 November: model and embedding digests, prompts, tool/query versions, verifier rules, corpus/chunk manifest, test questions/gold, retrieval top-k/threshold, generation limits and timeout policy. Save checksums in an experiment manifest. Prompt/model tuning uses only development questions and ends before freeze. Run final experiments on 15–18 November, after the preceding task gates pass. If a final-run bug is found, preserve old results and log the deviation; any confirmatory evaluation after tuning needs fresh untouched cases or must be described as exploratory.

### Scoring rules

| Measure | Definition and handling |
|---|---|
| Complete correct-answer rate | Questions meeting all required facts/action/scope and containing no unsupported substantive addition / all questions; report answerable subset separately |
| Required-fact recall | Correct required atomic facts / required atomic facts on answerable parts; abstentions do not earn credit |
| Numeric accuracy | Correct numeric fields / required numeric fields; counts/IDs exact, displayed percentage tolerance ±0.1 percentage points unless a stricter gold tolerance is specified |
| Unsupported claim rate | Unsupported factual claims / all factual claims; no-claim responses have N/A, not a perfect score |
| Answer coverage | Answerable questions with a substantive attempt / answerable questions; partial answers and their fact recall reported separately |
| Citation validity | References resolve to supplied, version-correct evidence / references emitted |
| Citation support precision | Claims whose cited material actually supports the claim / cited factual claims; assess semantics, scope and numbers |
| Citation support coverage | Factual claims with supporting citations / factual claims requiring evidence |
| Abstention/clarification | Correct unsupported-case action counts; abstention precision/recall on explicitly abstention-labeled questions, and clarification accuracy separately |
| Retrieval recall@4 | Gold supporting chunks retrieved in top 4 / gold supporting chunks for document questions; record multiple acceptable passages |
| Tool planning | Correct tool and scope selections / gold tool-required questions, plus invalid call count |
| Runtime | Median/p95 end-to-end latency, model/tool calls, input/output tokens, peak RAM/VRAM, timeout and schema/error rate |

Do not reward “always abstain.” Evaluate unsupported-claim rate with coverage and fact recall. A timed-out/error response stays in the denominator for end-to-end success. Citation ID existence is not semantic support. Count claims with wrong denominator, model/run or simulated-time interpretation as incorrect even if the numerical value happens to match.

Use deterministic comparisons for structured facts and human review for document claims, unsupported additions and answer usefulness. Blind the grader to condition labels where possible. Aim for independent peer/supervisor grading of at least 20 responses per condition, balanced across categories, with the source evidence visible; self-grade the full set using the same rubric. Record disagreements and adjudication. If no second grader is available, report single-author grading as a limitation, not independent validation. The generating LLM is never the sole judge.

Run one full evaluation of all arms. If the M1 timing estimate supports it, predeclare three repeats and apply them to every arm. Treat the **question** as the statistical unit; repeated answers are not new independent questions. Show raw counts and per-question paired differences; bootstrap question-level confidence intervals (e.g. 1,000 resamples, seed 42) for main rates/differences. With 48 questions, intervals may be wide; report them and avoid broad industrial generalization or strong significance claims.

Development goals, not guaranteed results: at least 85% complete correct answers on answerable questions, at least 85% coverage, no more than 5% unsupported claims, and at least 90% correct handling of unsupported cases. Freeze goals before testing. Missing a goal is a research finding; do not alter the benchmark or suppress failures to pass.

### Safety and correctness challenge cases

Include SQL-injection-like strings in filters, attempts to request write tools, a retrieved document that says to ignore rules, nonexistent evidence IDs, stale corpus/run IDs, empty batches, division by zero and timeouts. Verify that schema/authorization failures are visible and do not reach arbitrary SQL or shell execution. These are tests of the actual local boundary, not a claim of comprehensive security certification.

Also change a live run/quality record between two tool calls and confirm that both still return the question's original snapshot. Test same-asset records in different dataset versions and repeated inference runs, explicit left/right run selection in comparisons, and API evidence-persistence failure. A failed persistence step must not publish a successful unaudited answer.

## Evidence artifacts to retain

Under versioned run directories save manifests/configs, environment/locks, metrics JSON/CSV, model/checkpoint hashes, per-image predictions, error examples, question records, gold labels, original and checked LLM drafts, tool traces, evidence bundles, timing/resource logs and analysis scripts. Keep source data and large artifacts outside Git with acquisition/rebuild instructions. Preserve exact final report figure data and generation commands. Label fixtures, simulated batches and demonstration responses explicitly.

## Thesis report outline

1. **Introduction:** industrial analysis problem, data-engineering and LLM objectives, research questions and bounded contributions.
2. **Related work:** the six supervisor papers, anomaly versus supervised detection, retrieval/citation grounding, and the gap addressed by this evaluated system.
3. **Requirements and methodology:** user workflow, dataset suitability, hypotheses, local deployment constraints and experiment design.
4. **Architecture and implementation:** pipeline contracts, schema/lineage, detector integration, MCP tools, RAG, claim checks and failure recovery.
5. **Experiments and results:** dataset audit, pipeline baseline, detector results, main LLM comparisons, ablation, latency and error analysis.
6. **Discussion and limitations:** evidence of benefit or failure, coverage tradeoffs, data limitations, hardware, small sample/single-author bias and generalizability.
7. **Conclusion and future work:** answers to research questions grounded in actual findings; extensions justified by observed failures.
8. **References and appendices:** dataset/model factsheets, reproducibility runbook, metric/schema definitions, prompts/tool contracts, benchmark rubric and source inventory.

Use the university's required template, page limit and citation style once known. Do not invent experiments, claim supervisor approval or present this plan as a completed report. Suggested figures: architecture/data flow, lineage example, quality findings, per-class AP/error examples, LLM correctness-versus-coverage table, verification ablation and latency comparison.

## Defense and completion checklist

Demonstrate a small batch ingest and rerun, a quarantined bad sample, a defect overlay linked to its model/run, a chart with an explicit denominator, a numeric agent answer with SQL evidence, a contextual answer with a document citation, and an unsupported yield/causal question that is correctly declined. Open one saved answer's full evidence trace. Show final comparison results and one honest failure case.

Prepare a recorded backup and precomputed artifacts in case the live model is slow, labeled as recorded/cached. Keep at least one actual local question in the live demonstration when feasible. Show that no hosted LLM is required after downloading models.

The final submission package contains source/config/lockfiles, setup and restore instructions, data acquisition/citation instructions, model artifact references, reproducible results and analysis, final report, slides, demo recording, known limitations and third-party notices. Check the earlier official deadline if supplied. Actual upload/submission is a separate user action unless later explicitly authorized.
