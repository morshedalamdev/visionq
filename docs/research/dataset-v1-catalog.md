# NEU-DET v1 real catalog evidence — 26 November 2026

M2.T4 local real-data acceptance passed. Global M2.T4/M2 acceptance remains
**blocked** on mandatory rights-reviewed private Blob backup/restore and explicit
owner cloud authorization. No cloud access, training, commit or push occurred.

## Identity and results

Frozen export SHA-256:
`a8c14d88958f29a3042ba8b925584a9d6c770f60979cedb8bf9817ed393dc3c6`.
Dataset `NEU-DET`, version 1, evidence kind `released` (not synthetic).
Dataset version ID: `dc3b8671-354c-5393-930a-0e98cb0c04fd`.
Ingestion operation ID: `b280dfc2-b848-56f4-85ee-1eaae91a9f6b`.
Evidence: `artifacts/m2t4-real-9Sm1lP/`.

| Real version-scoped records | Count |
|---|---:|
| Dataset versions | 1 |
| Assets | 1797 |
| Annotation revisions | 1797 |
| Annotation boxes | 4182 |
| Allocation groups | 1661 |
| Dataset membership rows | 1797 |
| Content-addressed artifacts | 7175 |
| Quality records | 3779 |
| Ingestion operations | 1 |
| Per-item ingestion states | 1797 |

Quality records retain 1800 DQ02 warnings, 174 DQ03 filename warnings, 1800
DQ06 representation warnings, two DQ07 duplicate-conflict findings and three
review-quarantine records. They are not 3779 invalid released assets. The three exclusions and train/validation/test
1287/258/252 remain unchanged. Source/archive/acquisition/redistribution fields
remain unresolved/null rather than fabricated. Original metadata files, all raw
images/XML (including quarantines), approved release, frozen membership and
review/constraint evidence are retained as classified immutable artifacts.

## Actual verification

Two independent disposable PostgreSQL clusters were created with existing
`deploy/t4-postgres.sh` and migrated to `0007_upload_requests`. They are isolated
from the ordinary application database. Engine URLs point to loopback and database
`visionq_t4_test`; different cluster system identifiers were verified. All counts
above are scoped to the real package; regression fixtures add other isolated
synthetic dataset versions to these test clusters.

- Injected a controlled failure after 17 committed real assets. Persistent state
  became partial with exactly 17 succeeded items. Resuming the same operation
  completed all 1797; no duplicate logical records.
- Repeated import produced identical reconciliation and catalog snapshot.
- Repeated read-only reconciliation produced identical reports, no findings and
  no orphan artifacts; database snapshot unchanged.
- Full local rights-classified backup verified. Backup ID:
  `dd052420-7005-4134-9d40-8cec3b1187a6`.
- Backup manifest SHA-256:
  `84d2abb102ac3d94bd9f7f2f07f4ef588089383c2ab4446193387ab4051a0609`.
- Fresh independent restore produced an exactly matching catalog snapshot;
  all 7175 object hashes match, and post-restore reconciliation passed.
- All 3601 original files  / 28208067 bytes, frozen release and review bytes preserved.
- Initial focused run: 56 passed, 2 failures from changed expected error messages.
  Restored compatible messages without changing rejection behavior; nine targeted
  backup-damage cases passed. Failed logs retained.
- Strict full regression:328 passed, zero skipped, 63.76 s. Locked dependency,
  info, Ruff lint/format (88 files) and diff checks passed.
- Existing Foundation CI already discovers the new tests and enforces isolated
  PostgreSQL/no skips. Hosted CI for these uncommitted changes was not run.

Evidence scripts: `run-real.py` (fresh-database API execution), `checks.py`
(initial failure retained), `checks-repaired.py` (targeted repair/full gate), and
`final-cli-checks.py` (CLI and post-regression preservation). Command outputs and
exit codes remain beside them. Never rerun the fresh-database script on populated
clusters. `source-snapshot.json` and `restored-snapshot.json` prove logical row
agreement; artifact SHA-256 values prove byte identity. None establish source
rights, shared acquisition origin or model quality.

## Gates and continuation

V01 source/frozen identity:passed. V02 isolated schema:passed. V03 real import:
passed. V04 idempotency/conflicts:passed. V05 resume/crash boundaries:passed
(real 17-item interruption plus existing strict fixture recovery cases).
V06 reconciliation:passed. V07 local backup/restore:passed; required private Blob
portion blocked. V08 raw/frozen preservation:passed. V09 local module regression:
passed; global closeout blocked by V07 cloud boundary.

No cloud category is currently authorized. Review the metadata-only candidate
scope in catalog-runbook.md; full catalog JSON contains annotation data and must
not be uploaded merely because it is called metadata. Original/generated images,
XML/boxes, source metadata and model weights need explicit category decisions and
upload approval. Complete authorized Blob backup plus restore/integrity evidence
before marking M2 passed. No silent substitution of local tests for that gate.

[M3.T1 exact handoff](../operations/m3t1-real-training-kickoff.md) is prepared and
conditional on module-gate clearance and real-training authorization. No training
or device/model initialization was performed here.


Final real CLI repeat/status/reconciliation/backup verification all exited0.
After the full suite, real source and restored snapshots still matched the saved
pre-regression snapshot, all protected release/review bytes were unchanged, and
the backup verified under the final code. Both task-created containers were
stopped with volumes retained; see catalog-runbook.md for restart instructions.
