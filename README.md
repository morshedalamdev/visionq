# VisionQ

VisionQ is a research project for industrial defect detection and evidence-grounded
question answering. The intended product is a self-deployable application with
a public React dashboard that accepts live questions at any time.

The foundation provides an installable Python CLI. The worker source is in
`src/worker/`. The dashboard, detector, model services and public deployment
belong to later implementation stages.

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
