"""Shared catalog primitives; no ingestion policy or automatic repairs."""

import json
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import DateTime, MetaData, Table, Uuid, and_, select, text
from sqlalchemy.dialects.postgresql import insert

from worker.fixture import publish
from worker.inventory import canonical_json
from worker.validation import sha256

CATALOG_LOCK = 1448170548

KEYS = {
    "catalog_artifacts": ("sha256",),
    "dataset_versions": ("id",),
    "assets": ("id",),
    "annotation_revisions": ("dataset_version_id", "asset_id", "revision_sha256"),
    "annotations": ("dataset_version_id", "asset_id", "revision_sha256", "ordinal"),
    "dataset_groups": ("dataset_version_id", "group_id"),
    "dataset_items": ("dataset_version_id", "asset_id"),
    "quality_issues": ("id",),
    "ingestion_runs": ("id",),
    "ingestion_items": ("run_id", "asset_id"),
}


class CatalogBusy(RuntimeError):
    pass


class CatalogConflict(ValueError):
    pass


def plain(value):
    return json.loads(json.dumps(value, default=str, allow_nan=False))


def key_for(table_name, row):
    return canonical_json([plain(row[key]) for key in KEYS[table_name]]).decode()


def tables(connection):
    metadata = MetaData()
    return {name: Table(name, metadata, autoload_with=connection) for name in KEYS}


def values_for(table, row):
    result = {}
    for name, value in row.items():
        column = table.c[name]
        if column.computed is not None:
            continue
        if value is not None and isinstance(column.type, Uuid):
            value = UUID(str(value))
        elif value is not None and isinstance(column.type, DateTime):
            if isinstance(value, str):
                value = datetime.fromisoformat(value)
        result[name] = value
    return result


def predicate(table, row):
    values = values_for(table, row)
    return and_(*(table.c[name] == values[name] for name in KEYS[table.name]))


def ensure_row(connection, table, expected):
    connection.execute(
        insert(table).values(**values_for(table, expected)).on_conflict_do_nothing()
    )
    actual = (
        connection.execute(select(table).where(predicate(table, expected)))
        .mappings()
        .one_or_none()
    )
    if actual is None:
        raise CatalogConflict(f"{table.name}: conflicting unique identity")
    comparable = {name: plain(actual[name]) for name in expected}
    if comparable != plain(expected):
        raise CatalogConflict(f"{table.name}: existing row differs")


def object_path(root: Path, checksum: str):
    if len(checksum) != 64 or any(c not in "0123456789abcdef" for c in checksum):
        raise ValueError("invalid artifact checksum")
    root = root.absolute()
    for directory in (root, root / "catalog", root / "catalog/objects"):
        if directory.is_symlink():
            raise ValueError("artifact directory cannot be a symlink")
    path = root / "catalog/objects" / checksum
    if path.is_symlink():
        raise ValueError("artifact cannot be a symlink")
    return path


def check_blob(root, checksum, size):
    path = object_path(root, checksum)
    with path.open("rb") as stream:
        data = stream.read(size + 1)
    if len(data) != size or sha256(data) != checksum:
        raise CatalogConflict(f"artifact differs: {checksum}")


def store_blob(root, checksum, data):
    if sha256(data) != checksum:
        raise CatalogConflict("input artifact checksum differs")
    path = object_path(root, checksum)
    try:
        publish(path, data)
    except FileExistsError:
        pass
    check_blob(root, checksum, len(data))


@contextmanager
def writer(engine):
    with engine.connect() as connection:
        acquired = connection.scalar(
            text("SELECT pg_try_advisory_lock(:key)"),
            {"key": CATALOG_LOCK},
        )
        connection.commit()
        if not acquired:
            raise CatalogBusy("another catalog writer is active")
        try:
            yield connection
        finally:
            try:
                connection.rollback()
                connection.execute(
                    text("SELECT pg_advisory_unlock(:key)"),
                    {"key": CATALOG_LOCK},
                )
                connection.commit()
            except Exception:
                connection.invalidate()


def read_rows(connection, spec):
    reflected = tables(connection)
    version_id = UUID(spec["version_id"])

    asset_ids = {UUID(row["id"]) for row in spec["rows"]["assets"]}
    for name in ("annotation_revisions", "dataset_items", "quality_issues"):
        table = reflected[name]
        values = connection.scalars(
            select(table.c.asset_id).where(table.c.dataset_version_id == version_id)
        )
        asset_ids.update(value for value in values if value is not None)

    result = {}
    for name, table in reflected.items():
        statement = select(table)
        if name == "dataset_versions":
            statement = statement.where(table.c.id == version_id)
        elif name == "assets":
            statement = statement.where(table.c.id.in_(asset_ids))
        elif name == "catalog_artifacts":
            checksums = set(spec["artifacts"])
            checksums.update(
                connection.scalars(
                    select(reflected["assets"].c.raw_sha256).where(
                        reflected["assets"].c.id.in_(asset_ids)
                    )
                )
            )
            checksums.update(
                connection.scalars(
                    select(reflected["annotation_revisions"].c.source_xml_sha256).where(
                        reflected["annotation_revisions"].c.dataset_version_id
                        == version_id
                    )
                )
            )
            statement = statement.where(table.c.sha256.in_(checksums))
        else:
            statement = statement.where(table.c.dataset_version_id == version_id)
        result[name] = sorted(
            [plain(dict(row)) for row in connection.execute(statement).mappings()],
            key=lambda row: key_for(name, row),
        )
    return result
