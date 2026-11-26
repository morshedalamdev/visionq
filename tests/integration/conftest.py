"""Fixtures for the isolated T4 PostgreSQL integration tests.

Required environment (see docs/operations/catalog-runbook.md):

    VISIONQ_T4_SCHEMA_TEST=1           enable tests that need the shared T4 cluster
    VISIONQ_DATABASE_URL               loopback visionq_t4_test, migrated to head
    VISIONQ_T4_RESTORE_TEST=1          enable fresh-restore tests
    VISIONQ_RESTORE_DATABASE_URL       a different loopback cluster, migrated to head
    VISIONQ_REQUIRE_T4_TESTS=1         turn skips into failures (used by CI)
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import text

from worker.db import database

HEAD_REVISION = "0008_detector_evidence"


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.skipped and os.environ.get("VISIONQ_REQUIRE_T4_TESTS") == "1":
        reason = report.longrepr[2] if isinstance(report.longrepr, tuple) else ""
        report.outcome = "failed"
        report.longrepr = f"skipped while VISIONQ_REQUIRE_T4_TESTS=1: {reason}"


@pytest.fixture
def postgres_engine():
    if pytest.importorskip("psycopg") is None:
        pytest.fail("psycopg is required")

    if os.environ.get("VISIONQ_T4_SCHEMA_TEST") != "1":
        pytest.skip("requires the isolated T4 PostgreSQL database")

    if not os.environ.get("VISIONQ_DATABASE_URL"):
        pytest.fail("VISIONQ_DATABASE_URL must be explicit")

    engine = database()
    if engine.url.database != "visionq_t4_test":
        engine.dispose()
        pytest.fail("tests require database visionq_t4_test")
    if engine.url.host not in ("127.0.0.1", "localhost"):
        engine.dispose()
        pytest.fail("tests require loopback PostgreSQL")

    yield engine
    engine.dispose()


@pytest.fixture
def restore_engine(postgres_engine, monkeypatch):
    if os.environ.get("VISIONQ_T4_RESTORE_TEST") != "1":
        pytest.skip("requires the disposable T4 restore database")

    url = os.environ.get("VISIONQ_RESTORE_DATABASE_URL")
    if not url:
        pytest.fail("VISIONQ_RESTORE_DATABASE_URL must be explicit")
    if url == os.environ["VISIONQ_DATABASE_URL"]:
        pytest.fail("restore database must differ from the shared T4 database")

    with monkeypatch.context() as patch:
        patch.setenv("VISIONQ_DATABASE_URL", url)
        engine = database()

    problems = []
    if engine.url.database != "visionq_t4_test":
        problems.append("restore tests require database visionq_t4_test")
    elif engine.url.host not in ("127.0.0.1", "localhost"):
        problems.append("restore tests require loopback PostgreSQL")
    else:
        identity = text("SELECT system_identifier FROM pg_control_system()")
        with engine.connect() as restore, postgres_engine.connect() as shared:
            if restore.scalar(identity) == shared.scalar(identity):
                problems.append("restore database is the shared PostgreSQL cluster")
            revision = restore.scalar(text("SELECT version_num FROM alembic_version"))
        if revision != HEAD_REVISION:
            problems.append(f"restore database must be migrated to {HEAD_REVISION}")

    if problems:
        engine.dispose()
        pytest.fail("; ".join(problems))

    yield engine
    engine.dispose()
