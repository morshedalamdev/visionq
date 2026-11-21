"""Validate release inputs and construct immutable expected catalog records."""

import json
import random
from dataclasses import dataclass
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from worker.inventory import canonical_json, inventory
from worker.preparation import prepare, verify_export
from worker.review import check_review
from worker.validation import (
    CLASS_MAP_VERSION,
    CLASSES,
    audit,
    inspect_pair,
    sha256,
    validated_boxes,
)

FROZEN_SOURCE_SHA256 = (
    "3fec56c052f483a1a3abd3255c74e9f8502e0dd7ba156171852fa61060c7d4dc"
)
FROZEN_RELEASE_SHA256 = (
    "3ec61196f181354e3a01e57fef44f17446f5c7d555f4cf2fe070078859898125"
)
FROZEN_AUDIT_SHA256 = "d747b71a20460e471c06e65814d358db061bcf143fba13ef4da098d14e411f5b"
FROZEN_REVIEW_SHA256 = (
    "148077f47f8c944883f584d8134522941dbd4fd47b13c029da4b0e12d6db92fb"
)


def identity(kind, value):
    return str(uuid5(NAMESPACE_URL, f"visionq/catalog/v1/{kind}/{value}"))


def synthetic_sources():
    """The only source admitted during synthetic-only T4 development."""
    rng = random.Random(420019)
    result = {}
    for index in range(12):
        stem = f"synthetic_{index:02d}"
        result[f"IMAGES/{stem}.pgm"] = b"P5\n16 16\n255\n" + rng.randbytes(256)
        objects = "".join(
            f"<object><name>{name}</name><bndbox>"
            "<xmin>1</xmin><ymin>1</ymin><xmax>16</xmax><ymax>16</ymax>"
            "</bndbox></object>"
            for name in CLASSES
        )
        result[f"ANNOTATIONS/{stem}.xml"] = (
            f"<annotation><folder>synthetic</folder>"
            f"<filename>{stem}.pgm</filename>"
            "<size><width>16</width><height>16</height><depth>1</depth></size>"
            f"{objects}</annotation>"
        ).encode()
    return result


@dataclass
class Package:
    version_id: str
    run_id: str
    rows: dict
    blobs: dict
    categories: dict
    unit_artifacts: dict

    def specification(self):
        """Serializable expected state; contains no source bytes."""
        return {
            "format": "visionq-catalog-package-v1",
            "version_id": self.version_id,
            "run_id": self.run_id,
            "rows": self.rows,
            "artifacts": {
                checksum: {
                    "bytes": len(data),
                    "categories": sorted(self.categories[checksum]),
                }
                for checksum, data in sorted(self.blobs.items())
            },
            "unit_artifacts": self.unit_artifacts,
        }


def verified_source_bytes(source, observed, baseline_bytes, baseline_sha256):
    if baseline_sha256 == FROZEN_SOURCE_SHA256:
        if len(observed) != 48:
            raise ValueError("frozen synthetic source membership differs")
        result = {}
        for row in observed:
            path = Path(row["path"])
            if (
                path.is_absolute()
                or ".." in path.parts
                or not (
                    path.parts[0] == "IMAGES"
                    and path.suffix == ".png"
                    or path.parts[0] == "ANNOTATIONS"
                    and path.suffix == ".xml"
                )
            ):
                raise ValueError("frozen synthetic source membership differs")
            data = (source / path).read_bytes()
            if len(data) != row["bytes"] or sha256(data) != row["sha256"]:
                raise ValueError("frozen synthetic source bytes differ")
            result[row["path"]] = data
        if sha256(canonical_json(observed)) != FROZEN_SOURCE_SHA256:
            raise ValueError("frozen synthetic source baseline differs")
        if sha256(baseline_bytes) != FROZEN_SOURCE_SHA256:
            raise ValueError("frozen synthetic source baseline checksum differs")
        return result, "frozen-m3t2"

    fixture = synthetic_sources()
    actual_paths = {row["path"] for row in observed}
    if actual_paths != set(fixture):
        raise ValueError("source is not the admitted self-created fixture")
    for row in observed:
        expected = fixture[row["path"]]
        if (
            row["bytes"] != len(expected)
            or row["sha256"] != sha256(expected)
            or (source / row["path"]).read_bytes() != expected
        ):
            raise ValueError("source is not the admitted self-created fixture")
    return fixture, "generated-t4"


def load_package(
    source: Path,
    baseline: Path,
    packet: Path,
    release: Path,
    release_sha256: str,
    dataset_name: str,
    version: int,
):
    if not dataset_name.startswith("synthetic-"):
        raise ValueError(
            "real ingestion is disabled until T3 release authorization is accepted"
        )
    if type(version) is not int or version < 1:
        raise ValueError("dataset version must be a positive integer")

    observed, _ = inventory(source)
    baseline_bytes = baseline.read_bytes()
    if canonical_json(observed) != baseline_bytes:
        raise ValueError("source differs from the canonical baseline manifest")

    baseline_sha = sha256(baseline_bytes)
    source_bytes, source_kind = verified_source_bytes(
        source, observed, baseline_bytes, baseline_sha
    )

    verify_export(release, release_sha256)
    if source_kind == "frozen-m3t2":
        if release_sha256 != FROZEN_RELEASE_SHA256:
            raise ValueError("frozen synthetic release identity differs")
        if sha256((packet / "audit.json").read_bytes()) != FROZEN_AUDIT_SHA256:
            raise ValueError("frozen synthetic audit identity differs")
        if sha256((packet / "review.json").read_bytes()) != FROZEN_REVIEW_SHA256:
            raise ValueError("frozen synthetic review identity differs")
    exported = json.loads((release / "release.json").read_bytes())
    if exported.get("schema_version") != 1 or exported.get("status") != "released":
        raise ValueError("unsupported or incomplete export")

    receipt = check_review(packet)
    if exported["review_receipt"] != receipt:
        raise ValueError("export does not bind the current review receipt")

    report = json.loads((packet / "audit.json").read_bytes())
    if report.get("baseline_sha256") != baseline_sha:
        raise ValueError("audit baseline identity differs")
    revisions = [
        revision
        for item in report["items"].values()
        for revision in item["revision_history"]
    ]
    rebuilt = audit(
        source,
        baseline,
        sha256(baseline_bytes),
        report["coordinates"],
        revisions=revisions,
        reference=report["reference"],
    )
    if rebuilt != report:
        raise ValueError("audit cannot be reproduced from source and revisions")

    plan = prepare(source, packet)
    if exported["plan"] != plan:
        raise ValueError("exported plan differs from the reviewed source")
    if plan["class_map_version"] != CLASS_MAP_VERSION:
        raise ValueError("unsupported class map")
    if plan["classes"] != list(CLASSES):
        raise ValueError("class ordering differs")

    if plan["near_candidates"]:
        raise ValueError(
            "this synthetic fixture requires no unresolved near candidates"
        )

    config = {
        "importer": "visionq-catalog-v1",
        "evidence_kind": "synthetic",
        "dataset_name": dataset_name,
        "version": version,
        "source_manifest_sha256": sha256(baseline_bytes),
        "release_manifest_sha256": release_sha256,
        "audit_sha256": receipt["audit_sha256"],
        "review_sha256": receipt["review_sha256"],
        "class_map_version": CLASS_MAP_VERSION,
    }
    config_bytes = canonical_json(config)
    config_sha = sha256(config_bytes)
    version_id = identity("version", config_sha)
    run_id = identity("ingestion", version_id)

    rows = {
        name: []
        for name in (
            "catalog_artifacts",
            "dataset_versions",
            "assets",
            "annotation_revisions",
            "annotations",
            "dataset_groups",
            "dataset_items",
            "quality_issues",
        )
    }
    blobs = {}
    categories = {}

    def add_blob(data, category):
        checksum = sha256(data)
        if checksum in blobs and blobs[checksum] != data:
            raise ValueError("content identity conflict")
        blobs[checksum] = data
        categories.setdefault(checksum, set()).add(category)
        return checksum

    for path, data in source_bytes.items():
        add_blob(
            data,
            "original_images" if path.startswith("IMAGES/") else "annotations",
        )
    add_blob(baseline_bytes, "catalog_metadata")
    add_blob(config_bytes, "catalog_metadata")

    export_manifest = json.loads((release / "manifest.json").read_bytes())
    for member in export_manifest:
        category = (
            "generated_images"
            if member["path"].startswith("images/")
            else (
                "annotations"
                if member["path"].startswith("labels/")
                else "catalog_metadata"
            )
        )
        add_blob((release / member["path"]).read_bytes(), category)
    add_blob((release / "manifest.json").read_bytes(), "catalog_metadata")
    add_blob((packet / "audit.json").read_bytes(), "annotations")
    add_blob((packet / "review.json").read_bytes(), "annotations")

    rows["dataset_versions"].append(
        {
            "id": version_id,
            "dataset_name": dataset_name,
            "version": version,
            "evidence_kind": "synthetic",
            "source_identity_kind": "extracted_manifest_sha256",
            "source_identity": sha256(baseline_bytes),
            "source_manifest_sha256": sha256(baseline_bytes),
            "release_manifest_sha256": release_sha256,
            "importer_config_sha256": config_sha,
            "class_map_version": CLASS_MAP_VERSION,
            "archive_sha256": None,
            "acquisition_url": None,
            "acquired_at": None,
            "redistribution_terms": None,
        }
    )

    groups = {}
    unit_artifacts = {}
    assets_by_path = {}

    for record in plan["records"]:
        source_item = report["items"][record["source"]]
        asset_id = identity("asset", record["asset_id"])
        for alias in record["aliases"]:
            assets_by_path[alias] = asset_id

        decoded = source_item["decoded"]
        rows["assets"].append(
            {
                "id": asset_id,
                "raw_sha256": record["asset_id"],
                "pixel_sha256": record["pixel_sha256"],
                "width": record["width"],
                "height": record["height"],
                "channels": decoded["bands"],
            }
        )

        previous = groups.setdefault(record["group_id"], record["split"])
        if previous != record["split"]:
            raise ValueError("group crosses release splits")

        base = inspect_pair(
            source_bytes[record["source"]],
            source_bytes[source_item["xml"]],
            record["source"],
            report["coordinates"],
        )
        base_revision = sha256(
            canonical_json(
                {
                    "image_sha256": source_item["image_sha256"],
                    "xml_sha256": source_item["xml_sha256"],
                    "coordinates": report["coordinates"],
                    "class_map_version": CLASS_MAP_VERSION,
                }
            )
        )
        chain = [
            (
                base_revision,
                None,
                base["boxes"],
                {"kind": "source", "aliases": record["lineage"]},
            )
        ]
        previous_revision = base_revision
        for revision in source_item["revision_history"]:
            if revision["parent"] != previous_revision:
                raise ValueError("annotation revision chain differs")
            revision_sha = sha256(canonical_json(revision))
            chain.append(
                (
                    revision_sha,
                    previous_revision,
                    revision["boxes"],
                    {
                        "kind": "correction",
                        "aliases": record["lineage"],
                        "revision": revision,
                    },
                )
            )
            previous_revision = revision_sha

        if previous_revision != source_item["annotation_id"]:
            raise ValueError("active annotation identity differs")

        for revision_sha, parent, boxes, lineage in chain:
            rows["annotation_revisions"].append(
                {
                    "dataset_version_id": version_id,
                    "asset_id": asset_id,
                    "revision_sha256": revision_sha,
                    "source_xml_sha256": source_item["xml_sha256"],
                    "parent_revision_sha256": parent,
                    "lineage": lineage,
                }
            )
            checked = validated_boxes(boxes, record["width"], record["height"])
            for ordinal, box in enumerate(checked):
                rows["annotations"].append(
                    {
                        "dataset_version_id": version_id,
                        "asset_id": asset_id,
                        "revision_sha256": revision_sha,
                        "ordinal": ordinal,
                        "class_id": box[0],
                        "box_xmin": box[1],
                        "box_ymin": box[2],
                        "box_xmax": box[3],
                        "box_ymax": box[4],
                    }
                )

        if source_item["boxes"] != record["boxes"]:
            raise ValueError("release annotation differs from reviewed annotation")
        rows["dataset_items"].append(
            {
                "dataset_version_id": version_id,
                "asset_id": asset_id,
                "group_id": record["group_id"],
                "split": record["split"],
                "revision_sha256": previous_revision,
            }
        )
        unit_artifacts[asset_id] = sorted(
            {
                value
                for alias in record["lineage"]
                for value in (alias["image_sha256"], alias["xml_sha256"])
            }
        )

    rows["dataset_groups"] = [
        {
            "dataset_version_id": version_id,
            "group_id": group,
            "split": split,
        }
        for group, split in sorted(groups.items())
    ]

    findings = [(None, issue) for issue in report["issues"]]
    for path, item in sorted(report["items"].items()):
        findings.extend((path, issue) for issue in item["issues"])
        if path in plan["excluded"]:
            findings.append(
                (
                    path,
                    {
                        "rule": "review_quarantine",
                        "severity": "error",
                        "action": "exclude",
                    },
                )
            )

    for ordinal, (path, finding) in enumerate(findings):
        details = {"source": path, "finding": finding}
        rows["quality_issues"].append(
            {
                "id": identity(
                    "quality",
                    f"{version_id}:{ordinal}:{sha256(canonical_json(details))}",
                ),
                "dataset_version_id": version_id,
                "asset_id": assets_by_path.get(path),
                "rule_id": finding["rule"],
                "severity": finding["severity"],
                "details": details,
            }
        )

    rows["catalog_artifacts"] = [
        {
            "sha256": checksum,
            "byte_count": len(data),
            "artifact_uri": f"catalog/objects/{checksum}",
        }
        for checksum, data in sorted(blobs.items())
    ]

    return Package(
        version_id=version_id,
        run_id=run_id,
        rows=rows,
        blobs=blobs,
        categories=categories,
        unit_artifacts=unit_artifacts,
    )
