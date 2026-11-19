"""Read-only, deterministic catalog/artifact reconciliation."""

from pathlib import Path

from sqlalchemy import text

from worker.catalog_store import check_blob, key_for, read_rows
from worker.inventory import canonical_json


def compare_rows(spec, actual, require_success=True):
    findings = []

    def issue(kind, table, key, detail=None):
        findings.append({"kind": kind, "table": table, "key": key, "detail": detail})

    for name, expected_rows in spec["rows"].items():
        expected = {key_for(name, row): row for row in expected_rows}
        observed = {key_for(name, row): row for row in actual[name]}
        for key in sorted(expected.keys() - observed.keys()):
            issue("missing_record", name, key)
        for key in sorted(observed.keys() - expected.keys()):
            issue("unexpected_record", name, key)
        for key in sorted(expected.keys() & observed.keys()):
            selected = {column: observed[key].get(column) for column in expected[key]}
            if selected != expected[key]:
                issue("conflicting_record", name, key, selected)

    runs = actual["ingestion_runs"]
    if len(runs) != 1 or runs[0]["id"] != spec["run_id"]:
        issue("operation_identity", "ingestion_runs", spec["run_id"])
    else:
        run = runs[0]
        if run["expected_items"] != len(spec["rows"]["dataset_items"]):
            issue("operation_count", "ingestion_runs", spec["run_id"])
        if require_success and run["status"] != "succeeded":
            issue(
                "incomplete_operation",
                "ingestion_runs",
                spec["run_id"],
                run["status"],
            )

    expected_assets = {row["id"]: row["raw_sha256"] for row in spec["rows"]["assets"]}
    progress = {row["asset_id"]: row for row in actual["ingestion_items"]}
    if len(progress) != len(actual["ingestion_items"]):
        issue("duplicate_progress", "ingestion_items", spec["run_id"])

    for asset in sorted(expected_assets.keys() - progress.keys()):
        issue("missing_progress", "ingestion_items", asset)
    for asset in sorted(progress.keys() - expected_assets.keys()):
        issue("unexpected_progress", "ingestion_items", asset)
    for asset in sorted(expected_assets.keys() & progress.keys()):
        row = progress[asset]
        if (
            row["run_id"] != spec["run_id"]
            or row["dataset_version_id"] != spec["version_id"]
            or row["expected_raw_sha256"] != expected_assets[asset]
        ):
            issue("progress_identity", "ingestion_items", asset)
        if row["status"] != "succeeded" or row["catalog_asset_id"] != asset:
            issue("incomplete_item", "ingestion_items", asset, row["status"])

    return findings


def reconcile_connection(connection, root: Path, spec, require_success=True):
    actual = read_rows(connection, spec)
    findings = compare_rows(spec, actual, require_success=require_success)

    for checksum, artifact in sorted(spec["artifacts"].items()):
        try:
            check_blob(root, checksum, artifact["bytes"])
        except FileNotFoundError:
            findings.append(
                {
                    "kind": "missing_artifact",
                    "table": "catalog_artifacts",
                    "key": checksum,
                    "detail": None,
                }
            )
        except (OSError, ValueError) as exc:
            findings.append(
                {
                    "kind": "corrupt_artifact",
                    "table": "catalog_artifacts",
                    "key": checksum,
                    "detail": type(exc).__name__,
                }
            )

    registered = set(connection.scalars(text("SELECT sha256 FROM catalog_artifacts")))
    orphans = []
    directory = root / "catalog/objects"
    if directory.exists():
        for path in sorted(directory.iterdir()):
            if path.is_symlink() or not path.is_file():
                orphans.append(
                    {"path": path.name, "reason": "unsupported_storage_entry"}
                )
            elif path.name not in registered:
                orphans.append({"path": path.name, "reason": "unregistered_artifact"})

    findings.sort(key=lambda item: canonical_json(item))
    return {
        "format": "visionq-reconciliation-v1",
        "dataset_version_id": spec["version_id"],
        "run_id": spec["run_id"],
        "ok": not findings and not orphans,
        "findings": findings,
        "orphan_artifacts": orphans,
        "counts": {name: len(rows) for name, rows in sorted(actual.items())},
    }


def reconcile(engine, root: Path, spec):
    with engine.connect() as connection:
        connection = connection.execution_options(isolation_level="REPEATABLE READ")
        with connection.begin():
            connection.execute(text("SET TRANSACTION READ ONLY"))
            return reconcile_connection(connection, root, spec)


def report_text(report):
    lines = [
        f"dataset_version={report['dataset_version_id']}",
        f"run={report['run_id']}",
        f"ok={str(report['ok']).lower()}",
    ]
    lines.extend(
        f"{item['kind']} {item['table']} {item['key']}" for item in report["findings"]
    )
    lines.extend(
        f"orphan {item['path']} {item['reason']}" for item in report["orphan_artifacts"]
    )
    return "\n".join(lines) + "\n"
