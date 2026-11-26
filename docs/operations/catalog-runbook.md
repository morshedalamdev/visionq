# Catalog ingestion, backup and restore runbook (M2.T4)

Current acceptance: M2.T4/M2 passed on 26 November 2026 under the owner-approved hybrid architecture. See [hybrid recovery evidence](m2-hybrid-recovery-acceptance.md). Historical full-cloud-backup blockers below are superseded; the real catalog itself remains local-only, and only the six approved control files are stored in Blob.

Scope: the existing synthetic T4 catalog plus the **pinned, owner-authorized
NEU-DET v1** release. Other real datasets remain rejected. See the real-authorization
section below; synthetic names cannot bypass real-release verification.
Backups are local directories. No Azure/Blob transfer is implemented or authorized, and
a metadata-only backup is not artifact recovery: every backup here carries the verified
content-addressed objects it lists.

## Architecture in one page

| Piece | Contract |
|---|---|
| `catalog_*` tables (`0002_catalog`) | Immutable content identities; triggers reject UPDATE/DELETE, so a committed row cannot be compensated |
| `catalog.ingest` | One advisory-locked writer; artifact published before its database transaction; per-item transaction; at most three recorded attempts per item; `pending → running → succeeded / partial / failed` |
| `reconciliation.reconcile` | Read-only, repeatable-read; reports missing/corrupt/unregistered artifacts and row differences; never repairs |
| `catalog_backup.backup_catalog` | Reconciles and snapshots in one transaction; writes rights → members → objects → manifest; self-verifies the bundle **before** writing `COMPLETE`; create-only |
| `catalog_backup.restore_catalog` | Verifies the whole backup, stages and verifies artifacts, publishes the tree (`RESTORE_STATE.json` = `pending`), then commits PostgreSQL **last**, then marks `complete` |

### Why restore is ordered this way

PostgreSQL and the filesystem cannot commit together, and committed catalog rows cannot be deleted.
So the reversible step (filesystem) goes first and the irreversible step (commit) last:

| Failure point | Result | Recovery |
|---|---|---|
| Backup invalid / rights not approved / destination exists / version exists | Rejected before anything is written | Fix input |
| Before publication (including `os.replace` failure) | Staging and reservation removed; database untouched | Rerun |
| After publication, before commit (exception) | Rollback; this restore's destination removed (owner token checked) | Rerun |
| Process crash after publication, before commit | `RESTORE_STATE.json` = `pending`, database has no rows | Rerun the **same** command: destination bytes are re-verified, then the database phase runs |
| Commit succeeded, finalize failed or crashed | Rows committed, state `pending` | Rerun the same command: reconciles and marks `complete` |
| Commit outcome unknown | Destination kept; `RestoreIncomplete` raised | Rerun the same command |
| Pending destination tampered | Resume refuses and keeps the evidence | Inspect, remove it manually, rerun |

`state: complete` in `<destination>/catalog/RESTORE_STATE.json` is the only marker of a finished restore.
Never treat an existing destination without it as restored. A hard kill can leave a
`.catalog-restore-*` staging directory beside the destination; it holds no database state and is safe
to delete by hand.

## Environment variables

| Variable | Used by | Meaning |
|---|---|---|
| `VISIONQ_DATABASE_URL` | all `catalog-*` commands | `postgresql+psycopg://…`, loopback for restore. Without it, `POSTGRES_PASSWORD` selects the Compose `db` host |
| `VISIONQ_T4_SCHEMA_TEST=1` | integration tests | Opt in to the shared T4 cluster (`visionq_t4_test`, loopback) |
| `VISIONQ_RESTORE_DATABASE_URL`, `VISIONQ_T4_RESTORE_TEST=1` | restore tests | A **different** loopback cluster; its system identifier must differ |
| `VISIONQ_REQUIRE_T4_TESTS=1` | pytest | Turns any skipped test into a failure (CI) |
| `VISIONQ_T4_ENV_DIR` | `deploy/t4-postgres.sh` | Where cluster env files (mode 0600) are written; defaults to `$TMPDIR` |

## Disposable PostgreSQL

```zsh
deploy/t4-postgres.sh up source      # project visionq-t4-source, migrated to head
deploy/t4-postgres.sh up restore     # a second, independent cluster
. "$TMPDIR/visionq-t4-source.env";  export VISIONQ_DATABASE_URL="$VISIONQ_T4_URL"
. "$TMPDIR/visionq-t4-restore.env"; export VISIONQ_RESTORE_DATABASE_URL="$VISIONQ_T4_URL"
unset VISIONQ_T4_URL VISIONQ_T4_PASSWORD
export VISIONQ_T4_SCHEMA_TEST=1 VISIONQ_T4_RESTORE_TEST=1 VISIONQ_REQUIRE_T4_TESTS=1
uv run --locked python -m pytest -q -rs
deploy/t4-postgres.sh down restore   # removes only projects this script created
```

The script generates the password, never prints credentials, refuses to reuse an existing project, and
`down` refuses any project without its own env file. Tests never truncate or reset a database; they use
unique dataset names per test.

## Commands

Package arguments (`PKG`): `--source --baseline --packet --release --release-sha --dataset-name --version`.

```zsh
visionq catalog-import     $PKG --artifact-root ROOT           # idempotent; repeat is a verified no-op
visionq catalog-resume     $PKG --artifact-root ROOT --run-id ID   # only the matching operation
visionq catalog-status     --run-id ID                         # JSON; unknown id -> exit 1
visionq catalog-reconcile  $PKG --artifact-root ROOT           # exit 1 on any finding
visionq catalog-backup     $PKG --artifact-root ROOT --local-store DIR --backup-id UUID
visionq catalog-verify     --local-store DIR --backup-id UUID  # needs no database
visionq catalog-restore    --local-store DIR --backup-id UUID --destination NEW_DIR
```

Failures print one line to stderr (`<command> failed: …`) and exit 1; missing required options exit 2.
Database errors show only the exception type so connection details are never echoed.
`--local-store` is mandatory: there is no remote store option.

## Procedures

**Interrupted import.** `catalog-status` shows `partial` or `failed`. Run `catalog-resume` with the
run id; only incomplete items are redone. An item that failed three times needs review and is not
retried indefinitely. A completed import whose artifacts later change is reported by `catalog-import`
as "no longer reconciles"; it is never silently repaired.

**Reconciliation.** Run `catalog-reconcile`. `missing_artifact` / `corrupt_artifact` need the object restored
from a verified backup; `unregistered_artifact` is an orphan (reported, never deleted).

**Backup verification.** `catalog-verify` checks the marker, manifest, every member and object size and
checksum, the rights manifest, and the snapshot against the package specification.

**Fresh restore.** Use a new destination and a loopback database. Rerun the identical command after any
interruption. Then run `catalog-reconcile` with `--artifact-root DESTINATION`.

## Rights

Only `evidence_kind: synthetic` / `classification: synthetic-only` is accepted, on both backup and
restore. Released or otherwise classified data is rejected until a separate rights decision exists.
Do not upload NEU-DET or any dataset bytes to Azure or any remote store from this tooling.

## Troubleshooting

| Message | Meaning |
|---|---|
| `incomplete backup: COMPLETE missing` | Backup never finished; make a new one with a new id |
| `an earlier attempt left an incomplete backup` | Backup ids are create-only; choose a new id |
| `already contains version` | The database already has this dataset version; restore needs a database without it |
| `already exists:` / `already restored` | Destination exists or is finished; choose a new one |
| `RestoreIncomplete … rerun the same restore` | Follow the table above |
| `requires a loopback VISIONQ_DATABASE_URL` | Restore is local-only by policy |
| `catalog is not complete and reconciled` | Run `catalog-reconcile` first |

## Known limitations

- Real dataset ingestion, restore of real hashes and any cloud backup are blocked (T3 release, rights review, Azure authorization).
- Restoring into a database that already holds the same content-addressed rows is supported only for
  rows with identical content; `created_at` is the one tolerated difference.
- SQLAlchemy emits `SADeprecationWarning` for the `catalog_sha256` DOMAIN type during reflection
  (several thousand per full run). It does not affect behavior; address it when SQLAlchemy is upgraded.
- The commit-outcome-unknown window is handled by detection and resume; it cannot be forced in tests
  without a network fault, so it is covered by design and the resume tests rather than by injection.

## Real NEU-DET v1 authorization — 25 November 2026

This section supersedes the synthetic-only restriction above for exactly the
owner-approved private local NEU-DET version1 release. The synthetic contracts,
fixture table and existing catalog schema are unchanged. `worker.real_release`
allowlists the release, source, plan, component packet/review, constraint and frozen
membership hashes. It validates actual T2 review/audit, reconstructs component
policy, rechecks source/annotation lineage and runs export preflight. Other real
releases remain rejected. Missing evidence never falls back to a synthetic name.

All package-based catalog commands accept an evidence-location JSON through
`VISIONQ_REAL_AUTHORIZATION`. Its keys are `component_packet`,
`isolation_constraints`, `frozen_membership`; use absolute paths. This file supplies
locations, not arbitrary approval hashes. Code-pinned identities determine
admission. The config/catalog carries `evidence_kind=released`, exact authorization
hashes and receipt. Paths are not used to define immutable identity. Raw auxiliary
files are classified `source_metadata`, not mistaken for XML. Real release.json
and review/membership evidence carry annotations and are classified accordingly.

For the retained local evidence environment (credentials are in private mode0600
files; do not print them):

```zsh
cd /Users/morshedalam/Developer/AI/visionq
source artifacts/m2t4-real-9Sm1lP/visionq-t4-real9sm-source.env
export VISIONQ_DATABASE_URL="$VISIONQ_T4_URL"
unset VISIONQ_T4_URL VISIONQ_T4_PASSWORD
export VISIONQ_REAL_AUTHORIZATION="$PWD/artifacts/m2t4-real-9Sm1lP/authorization-locations.json"
```

The existing CLI arguments are unchanged. Name/version are `NEU-DET`/`1`, release
and pins are documented in dataset-v1-release.md. Use the dedicated source
cluster; do not change ordinary application records. Repeated import verifies a
no-op; it does not overwrite frozen membership. Refer to the evidence script
`artifacts/m2t4-real-9Sm1lP/run-real.py` for the actual API-level verification.
Do not rerun that fresh-database script against an already populated database.

### Rights boundary

Real local backup/restore uses only the concrete `Directory` adapter and records
`owner-authorized-private-local-only`, unresolved redistribution terms, and
`cloud_authorized=false`. Every included category explicitly permits only private
local backup/restore: catalog metadata, source metadata, original images,
annotations and generated images. This is the owner's operational authorization,
not an inferred dataset license. Restore verifies the same classification,
records/version identity and every required artifact; metadata-only is not full
recovery. Modified rights declarations and nonlocal adapters are rejected.

**No cloud category is authorized now.** Candidate metadata-only scope for a later
rights review: schema/migration version, opaque hashes/IDs, non-sensitive aggregate
counts, methodology and backup verification receipts. The current full catalog
snapshot includes boxes/lineage and cannot be treated as unrestricted metadata.
Original images, XML, generated images, annotation-bearing reports and model
weights require separately documented rights/eligibility and explicit upload
approval. Prepare a separately reviewed catalog/manifest backup scope before
private Blob transfer. No Azure calls or uploads occur in this implementation.
Mandatory private Blob backup/restore acceptance remains outstanding; do not mark
M2.T4 or M2 globally passed from local recovery alone.


### Retained verification clusters

The task-created `visionq-t4-real9sm-source-db-1` and
`visionq-t4-real9sm-restore-db-1` containers are stopped after verification; their
volumes, mode0600 credential files, snapshots and backup are retained. Restart
only these existing containers when needed:

```zsh
docker start visionq-t4-real9sm-source-db-1 visionq-t4-real9sm-restore-db-1
```

Then restore the environment variables above. Do not use `deploy/t4-postgres.sh up`
with those names: it correctly refuses existing projects. Do not remove volumes
until backup/evidence retention and recovery requirements are satisfied. The
ordinary application database was not touched.
