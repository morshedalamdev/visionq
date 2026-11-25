# VisionQ

VisionQ is a self-hosted industrial visual defect detection research project.
The Python worker inventories and validates NEU-DET, prepares reviewed releases,
and records YOLO11n training, evaluation and inference. FastAPI serves PostgreSQL
history, overlays and snapshot-based analytics to the React dashboard. Uploads
stage requests for inspection. Catalog registration, prediction of new uploads
and a live question-answering agent remain separate work.

The retrieval and five-tool read-only MCP interfaces have development-fixture
coverage. Real dataset release, held-out detector evaluation and live vLLM
acceptance remain open. The next private feasibility step is the M1.T3
model-access and serving preflight. The dashboard bearer credential is visible
to the browser. Use the single-operator loopback or SSH-tunnel boundary.

See the [current readiness record](docs/operations/m4-azure-readiness.md),
[deployment checklist](docs/operations/m1t3-deployment-checklist.md) and
[development plan](docs/plan/development-plan.md).

## Reproduce the foundation

Install uv, then run these commands from the repository root:

```sh
uv python install 3.11.17
uv sync --locked
uv run --locked visionq info
uv run --locked python -m worker info
uv run --locked python -m pytest -q
```

The two info commands should report the same application, version, interpreter
and platform. This foundation requires no model weights, dataset or cloud account.

## License

VisionQ's original source code is licensed under the
[GNU Affero General Public License, version 3 only](LICENSE).
Third-party software, model weights, and datasets retain their respective licenses.
