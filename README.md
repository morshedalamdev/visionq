# VisionQ

VisionQ is an industrial visual defect detection research project. The planned
React dashboard will let users upload an inspection image, see where the detector
finds suspected defects, and optionally ask questions about the recorded results.
Public visitors will be able to submit live questions at any time.

NEU-DET is the initial dataset for evaluating the detector. The project will
also be open source, with instructions for running your own copy using Docker.

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

## License

VisionQ's original source code is licensed under the
[GNU Affero General Public License, version 3 only](LICENSE).
Third-party software, model weights, and datasets retain their respective licenses.
