# Retrieval indexing and integrity runbook (M4.T2)

Scope: M4.T2 local implementation. The checked implementation supports
deterministically generated development embeddings and a replaceable
OpenAI-compatible private embedding adapter. It does not establish
EmbeddingGemma retrieval quality or live-service acceptance; those checks remain
part of M1.T3/M4 live integration.

## Corpus input

A corpus manifest uses `visionq-corpus-manifest-v1` and contains:

- corpus name, integer version and `development-fixture` or `approved` evidence
  class;
- unique document keys, document versions, titles and source-relative paths;
- optional source SHA-256 and document metadata;
- a versioned whitespace-token chunk configuration.

Source paths must remain below the explicitly selected corpus root and may not be
symlinks or absolute/traversal paths. UTF-8 content is required. Sources whose
paths contain benchmark, gold, grading, held-out, questions or expected-answer
markers are rejected. Before approving a production manifest, the reviewer must inspect the actual document content and its provenance against withheld questions, grading rubrics and reference answers. Record the reviewer, decision and exact source hashes. Path screening cannot establish corpus independence. Corpus approval is not granted by the implementation;
without approved documents, keep the evidence class `development-fixture`.

## Local indexing lifecycle

Use the typed `retrieval.build_index` service boundary:

1. parse and validate the manifest;
2. verify each source byte hash and prepare the resolved corpus manifest;
3. create immutable corpus, document and chunk rows idempotently;
4. create or resume one immutable embedding-profile index;
5. embed missing chunks in bounded batches and commit each batch;
6. mark the index ready only when persisted embedding count equals expected
   chunks;
7. return corpus/index IDs, manifest/profile SHA-256 values, counts and evidence
   class.

If indexing is interrupted, the committed batches remain; the index and corpus
record `failed`. Rerunning the same manifest and embedding profile completes
missing chunks without duplicating rows. A source change without a new corpus
version is rejected. A changed corpus version or embedding profile creates a
different identity and index.

## Retrieval and citations

`retrieval.search` accepts explicit corpus and index IDs, embeds the query with
the exact selected backend profile, and performs exact pgvector cosine search.
Ordering is score then chunk UUID, so ties are deterministic. Only `ready`
corpus/index pairs are queryable. The adapter rejects missing, incompatible,
non-finite or incorrectly dimensioned vectors.

Each result carries:

- corpus/index, document and chunk identities;
- document version and exact source-relative location;
- section title, text and source character offsets;
- document/chunk SHA-256 values;
- cosine-similarity score and explicit score semantics;
- backend/model/revision and corpus evidence class.

The development embedding backend is labeled
`deterministic-development` / `visionq-hash-unigram-v1`. Its output tests only
storage, isolation, ranking mechanics and citation contracts. It is not a
retrieval-quality or research result.

## Integrity and live acceptance boundary

`verify_index` rechecks the resolved manifest/source hashes, content counts,
profile identity, status and embedding completeness inside a repeatable-read
transaction. Document, chunk and embedding rows reject update/delete through
database triggers.

The `OpenAICompatibleEmbeddingBackend` is configured with a private base URL,
served model, revision, dimensions and optional query/document prefixes. Live
checks must verify both the actual pinned EmbeddingGemma model identity and
expected 768-dimensional finite vectors. Do not substitute hosted fallback
endpoints or present the deterministic backend's rankings as EmbeddingGemma
results.

