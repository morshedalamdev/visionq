"""Owner-authorized private NEU-DET v1 admission; no generic real-data bypass."""

import json
from pathlib import Path

from worker.component_review import POLICY_NAME, check_component_review
from worker.inventory import canonical_json
from worker.preparation import prepare
from worker.training import preflight
from worker.validation import sha256

RELEASE_SHA = "a8c14d88958f29a3042ba8b925584a9d6c770f60979cedb8bf9817ed393dc3c6"
SOURCE_SHA = "12d88cd4c70f984653ba6927729c0f584b29052895d0b0f32706b541dc6a1587"
PLAN_SHA = "0585278c54569a17c98142fa80250bf649c872ce5f2405a8942486b27f369b69"
PACKET_SHA = "c324d4df23a9f4c879c7aa4b097ec64ee959b6acbc4e954c3043da94038732c3"
REVIEW_SHA = "7193ec48d567394ccca0ea2b225d0ea96206dd435fc34396bd0bb6f1a88d83e8"
CONSTRAINT_SHA = "4af6862a012ba3a89f7626934f7cf669739d99122ed5b9e73eaf5a2d2d6079c9"
MEMBERSHIP_SHA = "508066a66900129626f2d9c6291dd7565ddfb278d53cf23f0b67faa8f6b8b41b"


def admit_identity(name, version, release_sha, baseline_sha, authorization):
    if (name, version, release_sha, baseline_sha) != (
        "NEU-DET",
        1,
        RELEASE_SHA,
        SOURCE_SHA,
    ) or authorization is None:
        raise ValueError(
            "real ingestion is disabled without the authorized NEU-DET v1 identity and evidence locations"
        )


def validate_real_release(source, baseline, packet, release, authorization):
    """Resolve evidence locations, verify fixed pins, and reconstruct the approved plan."""
    locations = json.loads(Path(authorization).read_bytes())
    component = Path(locations["component_packet"])
    constraints = Path(locations["isolation_constraints"])
    membership = Path(locations["frozen_membership"])
    if sha256(baseline.read_bytes()) != SOURCE_SHA:
        raise ValueError("real source baseline differs")
    if (
        sha256(constraints.read_bytes()) != CONSTRAINT_SHA
        or sha256(membership.read_bytes()) != MEMBERSHIP_SHA
    ):
        raise ValueError("real constraint or frozen membership differs")
    exported = json.loads((release / "release.json").read_bytes())
    plan = exported["plan"]
    if sha256(canonical_json(plan)) != PLAN_SHA:
        raise ValueError("real approved plan differs")
    receipt = check_component_review(component, PACKET_SHA, plan)
    if (
        receipt["review_sha256"] != REVIEW_SHA
        or exported["component_review_receipt"] != receipt
    ):
        raise ValueError("real component approval differs")
    frozen = json.loads(membership.read_bytes())
    if frozen["records"] != plan["records"] or frozen["plan_sha256"] != PLAN_SHA:
        raise ValueError("real frozen membership differs from plan")
    if (
        prepare(
            source,
            packet,
            grouping_policy=POLICY_NAME,
            isolation_constraints=constraints,
            isolation_constraints_sha=CONSTRAINT_SHA,
        )
        != plan
    ):
        raise ValueError("real source or approved isolation policy changed")
    preflight(release, RELEASE_SHA)
    evidence = [
        membership.read_bytes(),
        constraints.read_bytes(),
        (component / "packet.json").read_bytes(),
        (component / "component-review.json").read_bytes(),
    ]
    return plan, evidence
