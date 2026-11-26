# M2 hybrid recovery acceptance — 26 November 2026

**M2.T4 and M2 passed under the owner's approved hybrid architecture.** The owner
explicitly approved the architecture amendment and exact control-package digest,
then selected `/Volumes/250GB SSD` as the independent owner-controlled medium.
M2 and M6 requirements are updated consistently in development-plan.md,
architecture.md and azure-and-student-services.md. No complete-cloud recovery or
dataset rights claim is made. M6 still needs its own later project-level checks.

## Cloud result

Existing account/container: `stvisionq04df510c / visionq-backups`.
Account anonymous Blob access is disabled; container public_access is null.
Only six files /3615 bytes uploaded, under:
`m2t4-hybrid-control/9b85738ad6893f44c4cb642529357427863f847f7628d236c53870e2b08dedd9/`.
All uploaded/downloaded members match the approved inclusion digest:
`9b85738ad6893f44c4cb642529357427863f847f7628d236c53870e2b08dedd9`.

Payload: project-authored factual aggregate counts, opaque hashes, exclusions,
scope and instructions; no images, boxes, XML, labels, full catalog, per-image
membership, review text, credentials or weights. Existing full-backup category
permissions remain local-only. Owner authorization does not override third-party
restrictions. The package's historical proposal wording was preserved to keep
its approved bytes unchanged; actual owner authorization is recorded separately.

Anonymous access returned HTTP409, XML `PublicAccessNotPermitted`. Initial checker
expected401/403/404 and falsely failed. Original log/code retained; corrected
checker accepts409 only with that exact denial code, not arbitrary409 responses.
Authenticated remote existence/checksums and private properties were verified.
Fresh downloaded control package is byte-identical to the approved package.
No new cloud resources were created. No dataset/model bytes uploaded.

## Independent offline copy and actual restore

Complete backup root:
`/Volumes/250GB SSD/VisionQ-M2-v1-Bl5TQH/local-backup`.
Disk inspection verified external USB/APFS, Internal=false, writable and enough
space. The owner selected this unencrypted medium; physical custody and retention
remain their responsibility. A new create-only directory was used, with no
formatting, overwrites or changes to unrelated files.

Full backup:7180 files /117644072 bytes.
Backup ID:`dd052420-7005-4134-9d40-8cec3b1187a6`.
Manifest SHA-256:
`84d2abb102ac3d94bd9f7f2f07f4ef588089383c2ab4446193387ab4051a0609`.
Both the external copy and post-recovery copy verified against this digest.

The downloaded cloud anchor selected and verified that external full backup.
Restored into a new local PostgreSQL cluster with an empty catalog and a system
identifier different from both previous T4 clusters, at migration0007_upload_requests.
Actual restored snapshot exactly equals the original real ingestion snapshot:

| Records | Count |
|---|---:|
| Dataset versions |1|
| Assets / annotation revisions / memberships |1797 each|
| Boxes |4182|
| Allocation groups |1661|
| Immutable artifacts |7175|
| Quality records |3779|
| Ingestion operations / item states |1 /1797|

All7175 restored artifact hashes match. Read-only reconciliation has no findings
or orphans. Missing/corrupted control marker/anchor and missing/corrupted offline
objects were rejected using disposable copies; retained backups were not altered.
Original frozen distribution1287/258/252 and three quarantines are unchanged.
Cloud alone cannot reconstruct any catalog or dataset artifacts: both sources
remain essential. Safely eject/store the SSD offline after use, retain it through
the operations horizon, and include both-source availability in M6 rehearsals.

## Evidence and gate

Evidence root:`artifacts/m2-hybrid-acceptance-Bl5TQH/`.
Key files: rights-decision.json, offline-copy.json, cloud-access.json, upload/download
logs/exits, restore-database.json, negative-checks.json, restored-snapshot.json,
reconciliation.json, hybrid-results.json and final acceptance.json.
Original cloud-check failure is retained separately from corrected passing log.
No unrelated suites repeated; prior strict328-pass/no-skip gate remains valid.
Application code unchanged in this acceptance session; new evidence scripts reuse
existing Azure/Directory and catalog restore adapters. No commit/push or training.

**VM exception:** read-only Azure inspection found visionq-vm running. The agent
had not started it. The owner explicitly instructed “Leave it running; I will
handle it.” No VM start/stop/deallocation was executed. Do not report it deallocated.
This later owner instruction supersedes the initial task power-state constraint;
compute power/cost handling remains with the owner. The task-created local restore
container is stopped after verification, with its volume/evidence retained.

Next: [M3.T1 real training handoff](m3t1-real-training-kickoff.md). M2 dependency
is now cleared. Real training remains unexecuted; obtain the actual owner intended-
use decision, run the pinned device/data/weights preflight, then train only when
authorized. M6 offline services, full application restoration and rehearsal are
separate future acceptance obligations.
