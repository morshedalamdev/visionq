# VisionQ source inventory

## Foundation

- Python 3.11, uv, Hatchling, Typer, pytest and Ruff.
- Use pyproject.toml for direct declarations and uv.lock for resolved versions.
- Record the installed metadata and upstream license evidence under V06.
- Hatchling is an isolated build dependency. Record its pinned version separately.
- VisionQ-owned source license: decision pending. Record the chosen license,
  compatibility review and publication date before describing a release as open source.

## Research inputs

| Input                  | Upstream identity                                                                        | Decision to record                                                             |
| ---------------------- | ---------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| Generator              | Qwen/Qwen3-4B-Instruct-2507, candidate revision cdbee75f17c01a7cc42f958dc650907174af0554 | Apache-2.0 notices, self-hosting and distribution conditions                   |
| Embedder               | google/embeddinggemma-300m, candidate revision 57c266a740f537b4dc058e1b0cda161fd15afa75  | Gemma terms, account access, hosted use and distribution obligations           |
| Detector               | Ultralytics YOLO11n                                                                      | Code and pretrained-weight terms, trained outputs, public-service implications |
| Dataset                | Existing local NEU-DET directory                                                         | Provenance, terms, hashes and annotation audit in M2                           |
| Other local collection | NEU-CLS                                                                                  | Outside the planned detector study                                             |
| Original proposal      | docs/Thesis Proposal.docx                                                                | Preserve original bytes; confirm permission before public distribution         |

## V06 dated decisions

For each source record the date, publisher URL, revision or version, intended
use, applicable terms, access result, required notices and unresolved questions.

### Foundation dependency evidence — 15 November 2026

Installed distribution metadata in the project environment declared:

- MIT: annotated-doc 0.0.6, annotated-types 0.8.0, iniconfig 2.3.1,
  markdown-it-py 4.3.0, mdurl 0.1.2, pluggy 1.7.0, pydantic 2.14.3,
  pydantic_core 2.50.4, pytest 9.2.0, rich 15.0.0, ruff 0.17.5,
  typer 0.29.1, typing-inspection 0.4.5.
- BSD-2-Clause: Pygments 2.21.0.
- Apache-2.0 OR BSD-2-Clause: packaging 26.3.
- ISC: shellingham 1.5.4.
- PSF-2.0: typing_extensions 4.16.0.
- Build backend: hatchling 1.17.0, pinned in pyproject.toml.
- Local distribution: visionq 0.1.0. Its installed metadata does not
  currently declare a project license.
