# Technology stack and environment plan

Required choices for the reference implementation are below. This is a selection, not a record of installed dependencies. Keep the verified M1.T2 foundation lock. Add and lock dependencies when their task needs them. Record the separate host-specific serving images in deferred M1.T3 and freeze the experimental profiles before evaluation. Core stack documentation was checked on 21 October 2026; Azure/student-service choices were added on 13 November. A model candidate is not a promise of adequate speed on unmeasured hardware. See [Azure and student services](azure-and-student-services.md) for current benefit evidence, deployment limits and twelve-month costs.

## Required application stack

| Layer | Choice | Why it is needed |
|---|---|---|
| Language | Python 3.11 | One language for data, vision, API, agent and dashboard; compatible target for the current MCP SDK |
| Environment | uv, `pyproject.toml`, `uv.lock` | Reproducible dependencies; separate CPU/CUDA installation profiles |
| Image processing | OpenCV headless, NumPy, Pillow | Decode, inspect, convert channels, draw boxes and compute quality statistics |
| Vision | PyTorch, matching torchvision if required, Ultralytics YOLO11n | Fine-tune a small known-class detector and use its maintained evaluator |
| Tabular work | pandas | Dataset audits and small result exports; SQL remains the metric authority |
| Database | PostgreSQL 16 with pgvector | Metadata, lineage, metrics, answer traces and local document vectors in one service |
| DB access | SQLAlchemy 2, psycopg 3, Alembic | Typed persistence, parameterized queries and migrations |
| Runtime artifact storage | Host-local mounted filesystem, pathlib, hashlib | Immutable images/XML/manifests/checkpoints on laptop or VM persistent disk; no MinIO service required |
| Backup storage | Azure Blob Storage, `azure-storage-blob`, `azure-identity` | Explicit private backup/restore adapter with checksums and completion markers; not on the live answer path |
| Contracts | Pydantic 2 and pydantic-settings | Config, tool, evidence and answer validation |
| API | FastAPI and Uvicorn | Stable HTTP interface between dashboard and application services |
| Model serving (selected 15 November 2026) | vLLM in Docker: `vllm-gen` and `vllm-embed` | Separate generation and pooling servers can load the two models on one host |
| Generator candidate | [Qwen/Qwen3-4B-Instruct-2507](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507) | Instruction checkpoint with a chat template for tool plans and evidence-grounded answers |
| Embedding candidate | [google/embeddinggemma-300m](https://huggingface.co/google/embeddinggemma-300m) | Document and query vectors; 768 dimensions by default, 2,048 input tokens including formatting |
| Model client | One `httpx` adapter with two explicit internal base URLs | Send JSON over the vLLM OpenAI-compatible HTTP interface; enforce timeouts, validate responses, and fail on missing configuration |
| Agent | Small explicit Python state machine | Bounded tool selection, evidence assembly, checks and one repair; no framework dependency needed |
| MCP | Official `mcp` Python SDK, supported stable release line | Server/client for five tools over Streamable HTTP; verify the pinned API together |
| Document RAG | Section-aware text chunking + pgvector exact cosine search | Small auditable knowledge collection with citations; no separate vector database |
| Dashboard | Streamlit/Plotly in the original reference design | Image overlays, quality, run comparison and cited chat. See [project state](../agent/PROJECT_STATE.md) for the owner’s React/upload direction and open deployment decision |
| CLI/config | Typer, YAML via safe loader | Reproducible ingest/train/index/evaluate commands and configuration |
| Safe XML import | defusedxml | Parse downloaded annotations without resolving external entities |
| Testing | pytest, HTTP test client, small fixtures | Conversion, metrics, retries, MCP, retrieval and full local workflow checks |
| Code quality | Ruff; optional static type checking after basic checks pass | Keep one small codebase readable without building tooling for its own sake |
| Packaging | Docker Engine on Linux VM, Desktop locally; Compose v2 | Shared deployment, volumes, health checks and local offline demo |
| Azure infrastructure | One Linux VM, persistent managed disk, VNet/NSG, private Blob container, Entra identity, Cost Management | On-demand research compute after the Mac core, restricted SSH, backups and credit monitoring. Stage 1 identified the eastasia Standard_E4_v4 candidate. No VM provisioned |
| Infrastructure operation | Azure portal/CLI and OpenSSH | User-run setup, identity, SSH tunnels, cost checks and verified deallocation; no Terraform requirement for this small build |
| Version control and CI | Git, GitHub repository and GitHub Actions | Version source and run lightweight fixture checks; student Pro benefits subject to verified activation |
| Reporting | Markdown, exported CSV/JSON, Plotly/Matplotlib figures, university report format | Produce reproducible results and the final written thesis |

M1.T2 verified the foundation lock and pinned PostgreSQL 16/pgvector image. Build M2 against those contracts. The dataset/vision/analytics/UI paths must work without starting either inference service.

Record local and VM CPU architectures. Share source/configuration/model pins, but record and test platform-specific container digests and dependency profiles where ARM/x86 or CPU/CUDA differ. A multi-platform image index does not imply identical underlying platform images. Cache the correct local images and model weights for the offline restore; final LLM comparisons use one fixed host/image profile.

## Models, hardware and local operation

Use the two native model snapshots at the exact revisions in the [source inventory](../research/source-inventory.md). On M1.T3 resumption, verify access to those revisions and record SHA-256 manifests for weights, tokenizer, template, pooling and config files, and mount complete snapshots read-only. Record the vLLM version, image digest per platform, backend, dtype, quantization (if any) and effective launch settings separately. A model name or serving alias is not an artifact identity.

Recalculate memory when M1.T3 resumes. Four billion parameters at two bytes each represent roughly **8 GB for generator weights alone** (estimate, not process RAM). Add generator KV cache, embedding weights/process, database, app and host overhead. Sequential requests do not unload resident models. Bound context, concurrency and CPU KV-cache allocation explicitly; test both services resident together. Measure headroom on the candidate 32 GiB Standard_E4_v4 and the local defense host independently. If either fails, retain the evidence and review any development-only smaller-model or quantization trial with Architecture before freeze. The specified pair remains the approved research target. Do not reuse an old quantized package's size estimate.

M1.T1 recorded an Apple M4 with 16 GB of host RAM and a Linux ARM64 Docker guest with 7.75 GiB. The earlier small-model smoke test did not measure the approved two-model configuration. Recheck resources at resumption. Use a native-architecture Linux CPU container locally and a release-matched x86-64 CPU image on Azure. Inspect CPU instructions exposed inside each container and supported dtypes (EmbeddingGemma needs BF16 or FP32 activations, not FP16). If a compatible prebuilt image is unavailable, evaluate the official CPU Dockerfile at the pinned release. Do not assume Metal acceleration, emulation performance, NVIDIA hardware, or that every ARM machine supports the same image. [vLLM CPU installation and platform matrix](https://docs.vllm.ai/en/stable/getting_started/installation/cpu/).

YOLO training stays in the PyTorch worker. An available Linux GPU or measured native Mac training path may be useful for the detector; it is separate from vLLM serving and does not prove feasibility of either model server. [PyTorch installation](https://pytorch.org/get-started/locally/).

After the Mac core, resumed M1.T3 must measure model load, one embedding batch, structured answer validity, tool-plan success, median latency and peak RAM inside the actual Azure container environment, and verify a cached-model smoke path locally. The required five scoped questions must each finish without OOM and within 120 seconds end to end on the selected primary host. This is a development gate, not the final quality result. If it fails, record the failure and actual configuration, then investigate context/output limits, available hardware and the development fallback described above. Record any later approved change before benchmark freeze. GPU availability and CPU inference feasibility remain unverified. The dated Azure quota and public price checks are recorded in the [Azure plan](azure-and-student-services.md). Refresh them before provisioning.

Download once after checking rights. At runtime serve local snapshot **paths**, set `HF_HUB_OFFLINE=1` and `VLLM_NO_USAGE_STATS=1`, and test cold server startup with external egress blocked but internal Compose DNS/networking available. The flags do not themselves block all egress. Keep gated-download credentials out of images, runtime containers and logs. Blob backup needs network access separately; restored inference must not. [Hugging Face offline settings](https://huggingface.co/docs/huggingface_hub/package_reference/environment_variables), [vLLM usage statistics](https://docs.vllm.ai/en/stable/usage/usage_stats/). The Azure cost limits and local fallback still apply.

## Current documentation and license checks

| Source | Use and implementation caution |
|---|---|
| [Ultralytics YOLO11](https://docs.ultralytics.com/models/yolo11/) and [validation](https://docs.ultralytics.com/modes/val/) | `yolo11n.pt` is a supported chosen baseline; record evaluator arguments explicitly and do not rely on changing defaults |
| [Ultralytics licensing](https://www.ultralytics.com/license) | Package/weights have licensing conditions; preserve notices and check the chosen distribution against university publication plans |
| [PostgreSQL constraints](https://www.postgresql.org/docs/16/ddl-constraints.html) | Use unique/FK/check constraints plus service validation |
| [pgvector](https://github.com/pgvector/pgvector) | Exact cosine search is enough at this scale; pin extension and database image |
| [vLLM compatible server](https://docs.vllm.ai/en/stable/serving/online_serving/openai_compatible_server/) and [structured outputs](https://docs.vllm.ai/en/stable/features/structured_outputs/) | Send the JSON Schema for a plan/draft to the generation endpoint. Schema validity is separate from factual validity; the application validates the plan and executes allowed tools |
| [vLLM embedding task and supported models](https://docs.vllm.ai/en/stable/models/pooling_models/embed/) | Use the pooling server, model-specified query/document formats and the same pinned vector dimension at index and query time |
| [MCP Python SDK](https://py.sdk.modelcontextprotocol.io/) and [server transport](https://py.sdk.modelcontextprotocol.io/run/) | Current v2 docs use `MCPServer`; do not copy old `FastMCP` imports into v2 code |
| [FastAPI](https://fastapi.tiangolo.com/), [Pydantic](https://docs.pydantic.dev/latest/), [Streamlit](https://docs.streamlit.io/) | Typed interfaces and small dashboard; pin tested dependencies |

Preserve the M1.T1 rights inventory. Confirm pretrained detector rights before acquiring or copying weights in the vision work. Complete the pinned generator/embedding terms, access and private-hosting verification in deferred M1.T3 Stage 2 before downloading either snapshot. The candidate generator card lists Apache 2.0. EmbeddingGemma is gated: the user must accept Google's terms and obtain download access before staging it. Keep access credentials out of the serving environment. Audit dataset acquisition/private-copy rights in **M2 before acquisition/cloud upload**; redistribution remains a separate publication check. Do not infer universal permission from research use or a public download URL.

## Deliberately excluded from the November build

Airflow/Prefect, Kafka, Spark, Kubernetes/AKS, Redis/Celery, a dedicated MLflow/Azure ML service, Data Factory, managed PostgreSQL, Azure AI Search, MinIO, hosted LLM APIs, a second vector database, detector architecture research, LLM fine-tuning, multi-agent orchestration and production multi-user access are unnecessary for the defined experiments. MCP and RAG are **included**, not stretch features. A general agent platform would only be justified by a concrete requirement that this five-tool agent cannot satisfy; none is currently present. GitHub Pro/Actions are selected development support; Codespaces is a setup contingency and Copilot Student a personal aid, neither a research runtime dependency. Do not add other Pack vendors solely for promotional credit.
