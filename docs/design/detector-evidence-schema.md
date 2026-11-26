# Detector research evidence — migration 0008

`detector_evidence` is separate from annotations, detections and image results.
Its primary key is the sealed manifest SHA-256. Each record stores kind,
dataset_version_id, model_id, optional evaluation_sha256, original manifest bytes,
full JSONB payload and registration time. The composite model/dataset foreign key
prevents cross-dataset relationships. Performance references its evaluation;
verified ingestion checks the complete lineage. A partial unique index allows one
authoritative evaluation per model. Update/delete triggers reject mutations.

`worker.evaluation_registry.register_evidence` verifies both existing seals,
export membership, predictions, selection and timing aggregates with the existing
verifiers. It checks registered checkpoint/training/selection/dataset/classes and
operating settings, then copies hash-checked manifest/member bytes into the local
content-addressed artifact store. JSONB retains exact AP and operating metrics,
per-class support/error counts, timing distributions, hardware, settings and
limitations. Repeated identical imports are no-ops; conflicting results fail.
No training, evaluation or timing measurements execute during registration.

CLI: `visionq inference-register-evidence --model-id ID --artifact-root ROOT
--evaluation DIRECTORY --evaluation-sha SHA --performance DIRECTORY
--performance-sha SHA --export DIRECTORY --export-sha SHA`.

Analytics adds `evaluation_links` to newly captured evidence, scoped by the
validated inference run's model and dataset. Results are explicitly model-level,
not filtered batch/class prediction statistics. Existing snapshots are never
rewritten; their payloads/hashes remain valid. New context snapshots inherit these
links, including through the existing MCP provenance route. Missing evidence
returns available=false. Synthetic-development evidence keeps its explicit label.

Migration adds one table/index/trigger, touching no old rows. Downgrade drops only
the new evidence table; use only on disposable migration-test databases once real
evidence is registered. Backup/transfer must include this table and referenced
artifact bytes; the earlier M2 catalog-only backup is not a complete M3 backup.
