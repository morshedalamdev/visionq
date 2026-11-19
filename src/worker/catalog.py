"""Idempotent, resumable ingestion of validated catalog packages."""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError

from worker.catalog_store import (
    CatalogConflict,
    check_blob,
    ensure_row,
    plain,
    predicate,
    store_blob,
    tables,
    writer,
)
from worker.reconciliation import reconcile_connection

UNIT_TABLES = (
    "assets",
    "annotation_revisions",
    "annotations",
    "dataset_items",
    "quality_issues",
)


def now():
    return datetime.now(timezone.utc)


def belongs(name, row, asset_id):
    if name == "assets":
        return row["id"] == asset_id
    return row.get("asset_id") == asset_id


def verify_existing_row(connection, table, expected):
    actual = (
        connection.execute(select(table).where(predicate(table, expected)))
        .mappings()
        .one_or_none()
    )
    if actual is None:
        raise CatalogConflict(f"{table.name}: completed record is missing")
    if {key: plain(actual[key]) for key in expected} != expected:
        raise CatalogConflict(f"{table.name}: completed record differs")


def publish_set(package, root, checksums):
    for checksum in sorted(checksums):
        store_blob(root, checksum, package.blobs[checksum])


def artifact_rows(package, checksums):
    wanted = set(checksums)
    return [row for row in package.rows["catalog_artifacts"] if row["sha256"] in wanted]


def persist_failure(connection, reflected, run_id, message):
    runs = reflected["ingestion_runs"]
    progress = reflected["ingestion_items"]
    completed = connection.scalar(
        select(progress.c.asset_id)
        .where(progress.c.run_id == UUID(run_id))
        .where(progress.c.status == "succeeded")
        .limit(1)
    )
    connection.execute(
        update(runs)
        .where(runs.c.id == UUID(run_id))
        .values(
            status="partial" if completed is not None else "failed",
            finished_at=now(),
            last_error=message,
        )
    )


def transient(exc):
    if not isinstance(exc, DBAPIError):
        return False
    return getattr(exc.orig, "sqlstate", None) in ("40001", "40P01")


def initialize(connection, reflected, package, root):
    unit_checksums = {
        checksum
        for checksums in package.unit_artifacts.values()
        for checksum in checksums
    }
    global_checksums = set(package.blobs) - unit_checksums
    publish_set(package, root, global_checksums)

    with connection.begin():
        for row in artifact_rows(package, global_checksums):
            ensure_row(connection, reflected["catalog_artifacts"], row)
        for name in ("dataset_versions", "dataset_groups"):
            for row in package.rows[name]:
                ensure_row(connection, reflected[name], row)
        for row in package.rows["quality_issues"]:
            if row["asset_id"] is None:
                ensure_row(connection, reflected["quality_issues"], row)

        ensure_row(
            connection,
            reflected["ingestion_runs"],
            {
                "id": package.run_id,
                "dataset_version_id": package.version_id,
                "expected_items": len(package.rows["dataset_items"]),
            },
        )
        for asset in package.rows["assets"]:
            ensure_row(
                connection,
                reflected["ingestion_items"],
                {
                    "run_id": package.run_id,
                    "dataset_version_id": package.version_id,
                    "asset_id": asset["id"],
                    "expected_raw_sha256": asset["raw_sha256"],
                },
            )


def process_item(connection, reflected, package, root, asset_id, hook):
    progress = reflected["ingestion_items"]
    condition = (progress.c.run_id == UUID(package.run_id)) & (
        progress.c.asset_id == UUID(asset_id)
    )

    with connection.begin():
        current = connection.execute(select(progress).where(condition)).mappings().one()

        if current["status"] == "succeeded":
            for checksum in package.unit_artifacts[asset_id]:
                check_blob(root, checksum, len(package.blobs[checksum]))
            for name in UNIT_TABLES:
                for row in package.rows[name]:
                    if belongs(name, row, asset_id):
                        verify_existing_row(connection, reflected[name], row)
            return

    while True:
        with connection.begin():
            current = (
                connection.execute(select(progress).where(condition).with_for_update())
                .mappings()
                .one()
            )
            if current["attempts"] >= 3:
                raise CatalogConflict(
                    "item exhausted its three recorded attempts; review required"
                )
            connection.execute(
                update(progress)
                .where(condition)
                .values(
                    status="running",
                    attempts=current["attempts"] + 1,
                    last_error=None,
                )
            )

        try:
            hook("before_publication", asset_id)
            publish_set(package, root, package.unit_artifacts[asset_id])
            hook("after_publication", asset_id)

            with connection.begin():
                for row in artifact_rows(package, package.unit_artifacts[asset_id]):
                    ensure_row(connection, reflected["catalog_artifacts"], row)

                for name in UNIT_TABLES:
                    for row in package.rows[name]:
                        if belongs(name, row, asset_id):
                            ensure_row(connection, reflected[name], row)

                connection.execute(
                    update(progress)
                    .where(condition)
                    .values(
                        status="succeeded",
                        catalog_asset_id=UUID(asset_id),
                        last_error=None,
                    )
                )
                hook("before_item_commit", asset_id)

        except Exception as exc:
            connection.rollback()
            message = f"{type(exc).__name__}: item processing failed"
            with connection.begin():
                connection.execute(
                    update(progress)
                    .where(condition)
                    .values(status="failed", last_error=message)
                )
            if transient(exc):
                continue
            raise

        hook("after_item_commit", asset_id)
        return


def ingest(engine, root, package, resume_run=None, hook=None):
    if resume_run is not None and str(resume_run) != package.run_id:
        raise CatalogConflict("resume run does not match validated inputs")

    if hook is None:
        hook = lambda stage, asset: None

    spec = package.specification()
    with writer(engine) as connection:
        with connection.begin():
            reflected = tables(connection)
            existing = (
                connection.execute(
                    select(reflected["ingestion_runs"]).where(
                        reflected["ingestion_runs"].c.id == UUID(package.run_id)
                    )
                )
                .mappings()
                .one_or_none()
            )

        if resume_run is not None and existing is None:
            raise CatalogConflict("requested resume operation does not exist")

        if existing is not None and existing["status"] == "succeeded":
            with connection.begin():
                report = reconcile_connection(connection, root, spec)
            if not report["ok"]:
                raise CatalogConflict(
                    "completed import no longer reconciles; no repair performed"
                )
            return report

        initialize(connection, reflected, package, root)
        with connection.begin():
            connection.execute(
                update(reflected["ingestion_runs"])
                .where(reflected["ingestion_runs"].c.id == UUID(package.run_id))
                .values(
                    status="running",
                    started_at=(
                        existing["started_at"]
                        if existing is not None and existing["started_at"] is not None
                        else now()
                    ),
                    finished_at=None,
                    last_error=None,
                )
            )

        try:
            for asset_id in sorted(package.unit_artifacts):
                process_item(connection, reflected, package, root, asset_id, hook)

            hook("before_operation_success", None)
            with connection.begin():
                report = reconcile_connection(
                    connection, root, spec, require_success=False
                )
                if not report["ok"]:
                    raise CatalogConflict("final reconciliation failed")
                connection.execute(
                    update(reflected["ingestion_runs"])
                    .where(reflected["ingestion_runs"].c.id == UUID(package.run_id))
                    .values(
                        status="succeeded",
                        finished_at=now(),
                        last_error=None,
                    )
                )

        except Exception as exc:
            connection.rollback()
            with connection.begin():
                persist_failure(
                    connection,
                    reflected,
                    package.run_id,
                    f"{type(exc).__name__}: ingestion failed",
                )
            raise

        hook("after_operation_success", None)
        with connection.begin():
            return reconcile_connection(connection, root, spec)


def operation_status(engine, run_id):
    with engine.connect() as connection:
        with connection.begin():
            connection.execute(text("SET TRANSACTION READ ONLY"))
            reflected = tables(connection)
            run = (
                connection.execute(
                    select(reflected["ingestion_runs"]).where(
                        reflected["ingestion_runs"].c.id == UUID(str(run_id))
                    )
                )
                .mappings()
                .one_or_none()
            )
            if run is None:
                raise ValueError("unknown ingestion operation")
            progress = (
                connection.execute(
                    select(reflected["ingestion_items"]).where(
                        reflected["ingestion_items"].c.run_id == UUID(str(run_id))
                    )
                )
                .mappings()
                .all()
            )

    counts = {
        state: sum(row["status"] == state for row in progress)
        for state in ("pending", "running", "succeeded", "failed")
    }
    return {"operation": plain(dict(run)), "items": counts}
