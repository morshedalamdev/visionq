# Topic assessment and literature review

Reviewed on 21 October 2026. Evidence comes from the supplied topic, the six-paper attachment, the existing proposal, the supervisor repository, primary papers and official technical documentation. Paper methods and relevant experimental sections were read; this is a design-focused review, not a reproduction of their experiments.

## Recommended thesis direction

Original title: **A Data Engineering Framework for Industrial Visual Defect Detection Using Machine Learning**.

Recommended title to discuss with the supervisor: **A Data Engineering Framework for Industrial Visual Defect Detection and Evidence-Grounded Analysis Using a Local LLM Agent**.

Keep the approved title if the university requires it; the objectives and report must still make the LLM contribution explicit. The latest user requirements make local LLM research central, require completion of the project and report within November, and support MCP/RAG where they have a clear purpose.

The topic is suitable as an undergraduate systems research project if the detector is kept modest and the research centers on trustworthy data and answers. Training YOLO and drawing a dashboard alone would leave the LLM requirement unmet and provide a weak research comparison. The proposed contribution is a reproducible framework plus an empirical study of a local agent that combines exact database metrics, retrieved documentation, provenance and claim verification.

### Research questions

| ID | Question | Evidence to produce |
|---|---|---|
| RQ1 | Does explicit data validation and versioned ingestion improve pipeline reliability and traceability over a simple import script? | Injected-fault detection, duplicate-safe reruns, recovery and lineage audit |
| RQ2 | How well does a small supervised detector support analysis of the six NEU-DET defect classes? | Held-out per-class detection metrics and measured latency |
| RQ3, primary | Does a local MCP-connected agent using SQL evidence plus document RAG give more correct, supported answers than document RAG alone, and what does claim verification add? | Frozen QA benchmark, fair verification ablation, answer coverage, correctness, citations, abstention and latency |

The novelty claim is **an evaluated integration and domain-specific evidence contract**, not the invention of RAG, MCP, YOLO or a foundation model. Whether the work meets the institution's novelty threshold should be discussed with the supervisor in M1.T1; no approval has been obtained in this planning session.

## Supervisor repository audit

Repository: [zhouyu-hust/awesome-industrial-anomaly-detection](https://github.com/zhouyu-hust/awesome-industrial-anomaly-detection).

Inspected `main` at commit [`4e28b889b2c654d1d004b37cde856b3e6e5741a4`](https://github.com/zhouyu-hust/awesome-industrial-anomaly-detection/tree/4e28b889b2c654d1d004b37cde856b3e6e5741a4), dated 11 July 2026. It is a fork of M-3LAB's collection. The root contains `README.md`, `paper_tree.png` and `timeline.png`; it supplies a literature catalogue, not a runnable application or a pipeline to extend. No application license should be inferred from this collection.

Its taxonomy and dataset links help position the thesis. Much of the catalogue concerns anomaly detection, often learning normal appearance and detecting unseen deviations. NEU-DET instead supplies labeled examples of known defects for supervised object detection. These tasks have different data requirements and evaluation measures. Do not mix anomaly AUROC results with bounding-box mAP comparisons.

The README's NEU table is not authoritative for image channels or class structure. Use the [official NEU source](https://faculty.neu.edu.cn/songkechen/zh_CN/zdylm/263270/list/index.htm) and the actual downloaded archive. The source describes six grayscale defect categories. MVTec/PatchCore-style normal-only anomaly detection can be discussed in related work; implementing a second dataset/method is outside the November scope.

## Six supervisor papers

### P1 Hidden Technical Debt in Machine Learning Systems

D. Sculley et al. (2015). *Advances in Neural Information Processing Systems 28*, 2503–2511. [Primary PDF](https://papers.nips.cc/paper/2015/file/86df7dcfd896fcaf2674f757a2463eba-Paper.pdf).

Read §§2–8, especially data dependencies (§3), pipeline complexity (§5), configuration (§6), monitoring (§7), and Figure 1. The paper describes maintenance risks surrounding ML code, including hidden dependencies and feedback. It is a systems analysis, not an industrial defect benchmark.

**Design application:** explicit module interfaces, immutable source assets, versioned configurations, and separate labels and predictions. Every result must resolve to dataset, preprocessing and model versions. The project should demonstrate these properties rather than assert that architecture alone guarantees reliability.

### P2 An End-to-End Steel Surface Defect Detection Approach via Fusing Multiple Hierarchical Features

Yu He, Kechen Song, Qinggang Meng and Yunhui Yan (2020). *IEEE Transactions on Instrumentation and Measurement*, 69(4), 1493–1504. DOI [10.1109/TIM.2019.2915404](https://doi.org/10.1109/TIM.2019.2915404). [Accepted manuscript record](https://repository.lboro.ac.uk/articles/journal_contribution/An_end-to-end_steel_surface_defect_detection_approach_via_fusing_multiple_hierarchical_features/12249215).

Read the 13-page accepted manuscript, especially §V-A dataset, §V-C protocol, and §VI-D/Figure 12 failure cases. NEU-DET provides XML top-left/bottom-right boxes; the paper uses 1,260 training and 540 test images. Low contrast and confusing or fragmented textures are useful error-analysis slices.

**Design application:** inspect supplied boxes, record class and instance counts separately, and define a project validation split. Do not claim reproduction of its model. The accepted manuscript's Eq. (5) presents a nonstandard AP expression; use a maintained PR-curve evaluator, not that formula. Its headline mAP is not directly comparable to modern COCO-style mAP under our split.

### P3 You Only Look Once Unified Real-Time Object Detection

Joseph Redmon, Santosh Divvala, Ross Girshick and Ali Farhadi (2016). *CVPR*, 779–788. [Primary paper](https://arxiv.org/pdf/1506.02640); [CVF record](https://openaccess.thecvf.com/content_cvpr_2016/html/Redmon_You_Only_Look_CVPR_2016_paper.html).

Read §§2–4, covering unified detection, design and localization/error analysis. The original model predicts boxes and class information jointly and discusses speed/accuracy tradeoffs. Its architecture, confidence semantics and benchmark results belong to YOLO v1.

**Design application:** store image, class, box, score and model/run identifiers; evaluate localization as well as classification. Use current documentation for the chosen YOLO11 implementation. This thesis does not reproduce the 2016 network, and a modern confidence score must not be described as calibrated probability or as YOLO v1's exact score formula.

### P4 Data Validation for Machine Learning

Eric Breck, Neoklis Polyzotis, Sudip Roy, Steven Euijong Whang and Martin Zinkevich (2019). *Proceedings of Machine Learning and Systems 1*; the paper calls the event the 2nd SysML Conference. [Primary PDF](https://proceedings.mlsys.org/paper_files/paper/2019/file/928f1160e52192e3e0017fb63ab65391-Paper.pdf).

Read §§2–6, including schema lifecycle, single-batch validation, training-serving skew, synthetic tests and deployment evidence. Mathematical appendices were not exhaustively reviewed. The paper supports actionable schema checks and distribution comparisons, while recognizing incomplete rule coverage.

**Design application:** image decoding, annotation geometry and vocabulary checks, versioned severity/action rules, quarantine and fault-injection tests. Brightness or class-distribution shifts are review warnings, not automatic proof of factory drift. The image-specific rules are our adaptation, not a validation library supplied by this paper.

### P5 Datasheets for Datasets

Timnit Gebru, Jamie Morgenstern, Briana Vecchione, Jennifer Wortman Vaughan, Hanna Wallach, Hal Daumé III and Kate Crawford (2021). *Communications of the ACM*, 64(12), 86–92. DOI [10.1145/3458723](https://doi.org/10.1145/3458723). [Author manuscript v8](https://arxiv.org/pdf/1803.09010).

Read §§1–4, especially §3.2 composition, §3.3 collection, §3.4 preprocessing, §3.5 uses and §3.7 maintenance. The paper proposes reflective dataset documentation; it does not suggest that automatic statistics replace human documentation.

**Design application:** maintain a dataset factsheet separating published properties from archive observations and project transformations. Record absent normal examples, unknown timestamps, licensing uncertainty and intended uses. Our factsheet is a consumer's documentation of NEU-DET, not an assertion that we created the source dataset.

### P6 Accelerating the Machine Learning Lifecycle with MLflow

Matei Zaharia et al. (2018). *IEEE Data Engineering Bulletin*, 41(4), 39–45. [Author-hosted PDF](https://people.eecs.berkeley.edu/~matei/papers/2018/ieee_mlflow.pdf).

Read §2 and §§3.1–3.3 on Tracking, Projects and Models, plus §4 use cases. The paper connects parameters, code, metrics, artifacts and environments through open interfaces. It predates current registry features and does not establish current package behavior.

**Design application:** record experiment provenance in PostgreSQL plus immutable artifact files. A separate MLflow service is unnecessary for this small study. The architecture adopts tracking principles without claiming to implement MLflow or to guarantee identical GPU results across machines.

## Additional literature required by the LLM contribution

The supervisor's six papers do not evaluate LLM grounding. These two additions provide a starting point; they are not represented as supervisor-supplied papers.

### P7 Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks

Patrick Lewis et al. (2020). *NeurIPS 33*, 9459–9474. [Primary paper](https://arxiv.org/pdf/2005.11401).

Relevant reading: §2 model/retrieval design and §§3–4 evaluation. Retrieval supplies external evidence to a generator. The published system uses learned dense retrieval and generator training; VisionQ instead uses a fixed local model, a small versioned document corpus and database tools. We adopt the evidence-retrieval principle, not the paper's training method or performance claims.

### P8 Enabling Large Language Models to Generate Text with Citations

Tianyu Gao, Howard Yen, Jiatong Yu and Danqi Chen (2023). *EMNLP*, 6465–6488. [Publisher record and PDF](https://aclanthology.org/2023.emnlp-main.398/).

Relevant reading: §2 task definition, §§3.2–3.3 correctness and citation quality, §5.3 retrieval, and §6/Appendix F human evaluation. Citation presence alone does not establish that a claim is supported or that all claims have evidence. VisionQ adapts citation correctness/completeness assessment to short industrial analytics answers and combines it with deterministic numeric and scope checks. Its small domain benchmark is not an ALCE reproduction.

## Synthesis and scope decisions

| Decision | Reason and consequence |
|---|---|
| NEU-DET plus YOLO11n | Matches labeled defect localization and keeps CV implementation small |
| PostgreSQL plus immutable local files | Separates structured lineage/results from image and model bytes |
| Local LLM, SQL tools and document RAG | Supports factual metrics and contextual explanation with inspectable evidence |
| One read-only MCP server | Makes the agent/tool contract explicit and independently testable; MCP itself is not the research novelty |
| Verification and abstention | Testable mechanism for reducing unsupported answers without hiding loss of coverage |
| Small Python application with Docker Compose | Fits one student and a November deadline; a general agent platform has no demonstrated need |

The project cannot claim production yield, defect prevalence among all manufactured products, causal diagnosis, temporal factory trends, or unseen-defect detection from this dataset. A valid negative result is acceptable: if the local model fails to improve accuracy, report the measured tradeoff and failures rather than selecting only favorable questions.
