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
