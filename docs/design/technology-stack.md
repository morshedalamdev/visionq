# Technology stack and environment plan

Required choices for the reference implementation are below. This is a selection, not a record of installed dependencies. Verify a compatible set in M1, lock exact versions and image digests, and avoid changing them during final experiments. Official documentation was checked on 21 October 2026. A model candidate is not a promise of adequate speed on unmeasured hardware.

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
| Artifact storage | Local mounted filesystem, pathlib, hashlib | Immutable images/XML/manifests/checkpoints; no MinIO service required |
| Contracts | Pydantic 2 and pydantic-settings | Config, tool, evidence and answer validation |
| API | FastAPI and Uvicorn | Stable HTTP interface between dashboard and application services |
| Local LLM server | Ollama in Docker | Generator and embedding models served locally; cloud disabled |
| Generator candidate | `qwen3:4b-instruct-2507-q4_K_M` | Small local instruction model; evaluate tool planning and answer quality before freezing |
| Embedding candidate | `embeddinggemma:300m` | Local document and question embeddings; pin full digest and dimension |
| Model client | Ollama Python client or a single HTTP client adapter | Schema-constrained calls, timeouts and measured usage; choose one in M1 |
| Agent | Small explicit Python state machine | Bounded tool selection, evidence assembly, checks and one repair; no framework dependency needed |
| MCP | Official `mcp` Python SDK, supported stable release line | Server/client for five tools over Streamable HTTP; verify the pinned API together |
| Document RAG | Section-aware text chunking + pgvector exact cosine search | Small auditable knowledge collection with citations; no separate vector database |
| Dashboard | Streamlit, Plotly | Fast delivery of image overlays, data quality, metrics, run comparison and cited chat |
| CLI/config | Typer, YAML via safe loader | Reproducible ingest/train/index/evaluate commands and configuration |
| Safe XML import | defusedxml | Parse downloaded annotations without resolving external entities |
| Testing | pytest, HTTP test client, small fixtures | Conversion, metrics, retries, MCP, retrieval and full local workflow checks |
| Code quality | Ruff; optional static type checking after basic checks pass | Keep one small codebase readable without building tooling for its own sake |
| Packaging | Docker Engine/Desktop and Compose v2 | Reference local deployment, volumes, health checks and offline demo |
| Version control | Git | Version code, configuration, documentation and benchmark specifications |
| Reporting | Markdown, exported CSV/JSON, Plotly/Matplotlib figures, university report format | Produce reproducible results and the final written thesis |

PostgreSQL 16 is a deliberate supported baseline, not a claim that it is the newest release. Select a tested pgvector image/tag with that major version and pin its digest. No requirements file or lock is generated during this documentation-only task because the compatibility smoke test has not happened.

## Models, hardware and local operation

The [generator candidate](https://ollama.com/library/qwen3:4b-instruct-2507-q4_K_M) is a roughly 2.5 GB quantized model download. [EmbeddingGemma](https://ollama.com/library/embeddinggemma) is roughly 622 MB with a 2K input window; its page requires Ollama 0.11.10 or newer. Model file size is smaller than runtime memory demand. Pin complete model digests after pulling; tags can move.

Planning estimate: a laptop with 16 GB RAM and 25–40 GB free disk may support a small CPU demo if context and concurrency are limited; 24–32 GB RAM gives more headroom. These are unverified capacity estimates, not minimum certified requirements. Use one active answer at a time, short context, and sequential embedding/generation when memory is tight.

For training, seek an available Linux NVIDIA GPU; about 6–8 GB VRAM is a planning target for a small detector with reduced batch size, not a guarantee. If none is available, benchmark CPU training immediately and reduce epochs/batch/input size before committing the experiment schedule. A native Mac training run may be used if measured and documented, but the requested reference AI inference deployment remains Docker. Do not promise that Docker on macOS can use Apple Metal. [PyTorch install selector](https://pytorch.org/get-started/locally/), [Ollama Docker](https://docs.ollama.com/docker), [Ollama FAQ](https://docs.ollama.com/faq).

M1 must measure model load, one embedding batch, structured answer validity, tool-plan success, median latency and peak RAM inside the actual container environment. Proposed feasibility gate: five simple scoped questions finish without OOM and within 120 seconds each. This is a development gate, not the final quality result. If it fails, reduce context/output limits, test a smaller local model, or use available local Linux GPU hardware. Record any changed model before benchmark freeze; do not silently replace local inference with a paid/cloud endpoint.

Initial download uses the internet. Runtime uses local model files, `OLLAMA_NO_CLOUD=1`, a private service network, and no externally fetched evidence. Model inference and local training need no API subscription. Hardware/cloud rental costs are unknown and no paid resource is authorized or assumed.

## Current documentation and license checks

| Source | Use and implementation caution |
|---|---|
| [Ultralytics YOLO11](https://docs.ultralytics.com/models/yolo11/) and [validation](https://docs.ultralytics.com/modes/val/) | `yolo11n.pt` is a supported chosen baseline; record evaluator arguments explicitly and do not rely on changing defaults |
| [Ultralytics licensing](https://www.ultralytics.com/license) | Package/weights have licensing conditions; preserve notices and check the chosen distribution against university publication plans |
| [PostgreSQL constraints](https://www.postgresql.org/docs/16/ddl-constraints.html) | Use unique/FK/check constraints plus service validation |
| [pgvector](https://github.com/pgvector/pgvector) | Exact cosine search is enough at this scale; pin extension and database image |
| [Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs) and [tool calling](https://docs.ollama.com/capabilities/tool-calling) | Schema validity is separate from factual validity; the application executes allowed tools |
| [Ollama embeddings](https://docs.ollama.com/capabilities/embeddings) | Same embedding model/digest and dimension for indexing and querying |
| [MCP Python SDK](https://py.sdk.modelcontextprotocol.io/) and [server transport](https://py.sdk.modelcontextprotocol.io/run/) | Current v2 docs use `MCPServer`; do not copy old `FastMCP` imports into v2 code |
| [FastAPI](https://fastapi.tiangolo.com/), [Pydantic](https://docs.pydantic.dev/latest/), [Streamlit](https://docs.streamlit.io/) | Typed interfaces and small dashboard; pin tested dependencies |

Record model and dataset notices in a dependency/source inventory during M1/M2. The candidate generator page lists Apache 2.0; EmbeddingGemma has its own model terms and must be checked separately. Dataset redistribution rights remain unresolved. Do not infer universal permission from research use or a public download URL.

## Deliberately excluded from the November build

Airflow/Prefect, Kafka, Spark, Kubernetes, Redis/Celery, a dedicated MLflow service, MinIO, hosted LLM APIs, a second vector database, detector architecture research, LLM fine-tuning, multi-agent orchestration and production multi-user access are unnecessary for the defined experiments. MCP and RAG are **included**, not stretch features. A general agent platform would only be justified by a concrete requirement that this five-tool agent cannot satisfy; none is currently present.
