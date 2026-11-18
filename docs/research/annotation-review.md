# Annotation validation and review protocol

M2.T2 implementation and verification are pending until its recorded gate passes.

## Preserved source and identities

Use the T1 NEU-DET manifest and its SHA-256 as the source reference.
Keep original image and XML bytes, source paths and raw class spellings.
The class map is neu-det-v1. Source rolled-in_scale maps explicitly to
canonical rolled_in_scale, class ID 4.

An audit records its ruleset, class map, coordinate candidate, limits,
library versions, raw hashes, decoded metadata, source object fields,
canonical boxes, quality findings and annotation revision identities.

## Coordinate review

Compare one-based inclusive and zero-based half-open candidate overlays.
Inspect at least five distinct images containing each class, including
border cases. Inspect every object in each selected image.

Source bounds spanning 1 through 200 support investigation of one-based
inclusive coordinates. They do not independently establish endpoint semantics.

Record the adopted project convention and its evidence in review.json.
Retain source_endpoint_semantics as unverified unless separate evidence is
reviewed. Canonical boxes use zero-based half-open edges. Conversion never clips
invalid boxes.

## Quality and quarantine

DQ01 checks bounded complete decoding.
DQ02 checks source geometry, mode and orientation.
DQ03 checks safe XML, complete annotation structure and pairing.
DQ04 checks explicit vocabulary and aliases.
DQ05 checks finite, ordered, nonempty, in-bounds canonical geometry.
DQ06 checks decoded width/height against XML declarations. A depth/band
representation discrepancy is retained as a review warning.
DQ07 reports identical bytes or decoded pixels and conflicting annotations.
DQ08 checks group membership across splits. Real memberships await M2.T3.
DQ09 binds source files to the verified manifest.
DQ10 compares class support and available brightness statistics with a recorded
reference. These are image-data warnings, without production-drift claims.

Quarantine is logical. Reports retain original paths and reasons.
The effective quarantine is the union of automated findings and human review
dispositions. T3 must honor that union.

## Corrections

A correction records author, reason, time, source hashes, coordinate convention,
class-map version, parent revision and the full replacement canonical box list.
Original XML remains preserved. Existing revision bundles are create-only.

This interface supports class and box corrections on structurally inspectable
inputs. Structural image/XML failures remain quarantined for explicit review.

## Required review evidence

Keep both coordinate candidate reports and packets.
For the selected interpretation, complete review.json with reviewer, time,
coordinate basis, warning disposition and a decision/notes for every item.
Run check-review and retain its receipt.

Review the byte-identical patches_101.jpg and patches_105.jpg pair separately.
Their original XML boxes differ. Retain both in quarantine while the conflict
is unresolved. Any correction requires an actual human decision.

Save actual accepted/quarantined counts, warning dispositions, review coverage,
report hashes and revision IDs after running the checks. Dataset release,
duplicate/acquisition-group freezing and test membership remain M2.T3 work.

## Applied evidence — 18 November 2026

Automated repair evidence: `artifacts/m2t2-repair-pBMtK3/` (52 passing tests,
1,800 decoded images for each candidate; 2 quarantined images). Both audits have
1,800 DQ02 warnings, 174 DQ03 warnings, 1,800 DQ06 warnings and 2 DQ07 errors.
The quarantined byte-identical patches_101/patches_105 annotations conflict.
Source endpoint semantics remain unverified. One-based-inclusive is the working
candidate; no final human-review approval is inferred.

Current one-review/review.json has 6 accept and 23 pending decisions. The existing
validator rejects the pending inclusion_10 decision. T2 remains open; no passing
real review receipt or correction exists. Preserve the actual review record.

Reconciliation: artifacts/m2t3-development/T2-reconciliation.json.
Source preservation and tested code hashes: preservation.json and code-hashes.json
in that evidence directory. The final integration suite passes 62 tests; fixtures
are software evidence only. The user authorized T3 development with T2 pending,
but real export refuses incomplete review. See dataset-preparation.md.
