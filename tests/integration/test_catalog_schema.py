"""Opt-in PostgreSQL schema tests using synthetic identities only."""

import os
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from worker.db import database


@pytest.fixture
def connection():
    if os.environ.get("VISIONQ_T4_SCHEMA_TEST") != "1":
        pytest.skip("requires the isolated T4 PostgreSQL database")

    if not os.environ.get("VISIONQ_DATABASE_URL"):
        pytest.fail("explicit isolated database URL is required")

    engine = database()
    if engine.url.database != "visionq_t4_test" or engine.url.host not in (
        "127.0.0.1",
        "localhost",
    ):
        engine.dispose()
        pytest.fail("schema tests require loopback visionq_t4_test")

    try:
        with engine.connect() as conn:
            transaction = conn.begin()
            try:
                assert conn.scalar(text("SELECT current_database()")) == (
                    "visionq_t4_test"
                )
                assert conn.scalar(text("SELECT version_num FROM alembic_version")) == (
                    "0002_catalog"
                )
                yield conn
            finally:
                transaction.rollback()
    finally:
        engine.dispose()


def add_version(conn, version_id, number):
    conn.execute(
        text("""
            INSERT INTO dataset_versions (
                id, dataset_name, version, evidence_kind,
                source_identity_kind, source_identity,
                source_manifest_sha256, release_manifest_sha256,
                importer_config_sha256, class_map_version
            ) VALUES (
                :id, 'synthetic-schema-test', :number, 'synthetic',
                'extracted_manifest_sha256', :source,
                :source, :release, :config, 'neu-det-v1'
            )
        """),
        {
            "id": version_id,
            "number": number,
            "source": "b" * 64,
            "release": "c" * 64,
            "config": f"{number:064x}",
        },
    )


@pytest.fixture
def catalog(connection):
    conn = connection
    for value in "abcd":
        conn.execute(
            text("""
                INSERT INTO catalog_artifacts (sha256, byte_count)
                VALUES (:sha, 100)
            """),
            {"sha": value * 64},
        )

    version_id, asset_id = uuid4(), uuid4()
    add_version(conn, version_id, 1)
    conn.execute(
        text("""
            INSERT INTO assets
                (id, raw_sha256, pixel_sha256, width, height, channels)
            VALUES (:asset, :raw, :pixels, 200, 200, 1)
        """),
        {"asset": asset_id, "raw": "a" * 64, "pixels": "e" * 64},
    )
    identity = {
        "version": version_id,
        "asset": asset_id,
        "revision": "e" * 64,
        "group": "f" * 64,
    }

    conn.execute(
        text("""
        INSERT INTO annotation_revisions (
            dataset_version_id,
            asset_id,
            revision_sha256,
            source_xml_sha256,
            lineage
        ) VALUES (
            :version,
            :asset,
            :revision,
            :xml,
            CAST(:lineage AS jsonb)
        )
    """),
        {
            **identity,
            "xml": "d" * 64,
            "lineage": '{"synthetic": true}',
        },
    )

    conn.execute(
        text("""
            INSERT INTO dataset_groups (dataset_version_id, group_id, split)
            VALUES (:version, :group, 'train')
        """),
        identity,
    )
    return conn, identity


def insert_item(conn, identity, split="train"):
    conn.execute(
        text("""
            INSERT INTO dataset_items (
                dataset_version_id, asset_id, group_id, split, revision_sha256
            ) VALUES (:version, :asset, :group, :split, :revision)
        """),
        {**identity, "split": split},
    )


@pytest.mark.parametrize(
    "box,valid",
    [
        ((0, 0, 200, 200), True),
        ((199, 199, 200, 200), True),
        ((-1, 0, 10, 10), False),
        ((10, 0, 10, 10), False),
        ((0, 0, 201, 10), False),
        ((0, 0, float("inf"), 10), False),
        ((float("nan"), 0, 10, 10), False),
    ],
)
def test_box_constraints(catalog, box, valid):
    conn, identity = catalog

    parameters = {
        **identity,
        **dict(
            zip(
                ("box_xmin", "box_ymin", "box_xmax", "box_ymax"),
                box,
                strict=True,
            )
        ),
    }

    statement = text("""
        INSERT INTO annotations (
            dataset_version_id,
            asset_id,
            revision_sha256,
            ordinal,
            class_id,
            box_xmin,
            box_ymin,
            box_xmax,
            box_ymax
        ) VALUES (
            :version,
            :asset,
            :revision,
            0,
            0,
            :box_xmin,
            :box_ymin,
            :box_xmax,
            :box_ymax
        )
    """)

    if valid:
        conn.execute(statement, parameters)
    else:
        with pytest.raises(IntegrityError), conn.begin_nested():
            conn.execute(statement, parameters)


def test_membership_and_lineage_constraints(catalog):
    conn, identity = catalog

    with pytest.raises(IntegrityError), conn.begin_nested():
        insert_item(conn, identity, split="test")

    second_version = uuid4()
    add_version(conn, second_version, 2)
    second = {**identity, "version": second_version}
    conn.execute(
        text("""
            INSERT INTO dataset_groups (dataset_version_id, group_id, split)
            VALUES (:version, :group, 'train')
        """),
        second,
    )
    with pytest.raises(IntegrityError), conn.begin_nested():
        insert_item(conn, second)

    insert_item(conn, identity)
    with pytest.raises(IntegrityError), conn.begin_nested():
        insert_item(conn, identity)

    with pytest.raises(IntegrityError), conn.begin_nested():
        conn.execute(
            text("UPDATE assets SET width = 100 WHERE id = :asset"),
            identity,
        )

    assert (
        conn.scalar(
            text("""
            SELECT count(*)
            FROM dataset_items
            WHERE dataset_version_id = :version
        """),
            identity,
        )
        == 1
    )


def test_identity_constraints(catalog):
    conn, identity = catalog
    invalid_statements = [
        ("INSERT INTO catalog_artifacts VALUES ('bad-hash', 1)", {}),
        (
            "INSERT INTO catalog_artifacts (sha256, byte_count) VALUES (:sha, -1)",
            {"sha": "9" * 64},
        ),
        (
            """INSERT INTO assets
            (id, raw_sha256, pixel_sha256, width, height, channels)
            VALUES (:id, :raw, :pixels, 200, 200, 1)""",
            {"id": uuid4(), "raw": "a" * 64, "pixels": "8" * 64},
        ),
        (
            """INSERT INTO assets
            (id, raw_sha256, pixel_sha256, width, height, channels)
            VALUES (:id, :raw, :pixels, 200, 200, 1)""",
            {"id": uuid4(), "raw": "9" * 64, "pixels": "8" * 64},
        ),
    ]
    for sql, parameters in invalid_statements:
        with pytest.raises(IntegrityError), conn.begin_nested():
            conn.execute(text(sql), parameters)

    row = conn.execute(
        text("""
            SELECT archive_sha256, acquisition_url, redistribution_terms
            FROM dataset_versions WHERE id = :version
        """),
        identity,
    ).one()
    assert tuple(row) == (None, None, None)


def test_progress_requires_matching_catalog_item(catalog):
    conn, identity = catalog
    run_id = uuid4()
    conn.execute(
        text("""
            INSERT INTO ingestion_runs (id, dataset_version_id, expected_items)
            VALUES (:run, :version, 1)
        """),
        {**identity, "run": run_id},
    )
    parameters = {**identity, "run": run_id, "raw": "a" * 64}
    conn.execute(
        text("""
            INSERT INTO ingestion_items (
                run_id, dataset_version_id, asset_id, expected_raw_sha256
            ) VALUES (:run, :version, :asset, :raw)
        """),
        parameters,
    )

    success = text("""
        UPDATE ingestion_items
        SET status = 'succeeded', catalog_asset_id = :asset, attempts = 1
        WHERE run_id = :run AND asset_id = :asset
    """)
    with pytest.raises(IntegrityError), conn.begin_nested():
        conn.execute(success, parameters)

    insert_item(conn, identity)
    conn.execute(success, parameters)
    assert (
        conn.scalar(
            text("SELECT status FROM ingestion_items WHERE run_id = :run"),
            parameters,
        )
        == "succeeded"
    )
