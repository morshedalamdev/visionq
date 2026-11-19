"""Connection configuration tests; no database connection is opened."""

import pytest

from worker.db import database


def test_foundation_defaults_are_preserved(monkeypatch):
    monkeypatch.delenv("VISIONQ_DATABASE_URL", raising=False)
    monkeypatch.setenv("POSTGRES_PASSWORD", "synthetic-password")
    engine = database()
    try:
        assert engine.url.drivername == "postgresql+psycopg"
        assert engine.url.host == "db"
        assert engine.url.database == "visionq"
        assert engine.url.username == "visionq"
    finally:
        engine.dispose()


def test_explicit_test_configuration(monkeypatch):
    monkeypatch.setenv(
        "VISIONQ_DATABASE_URL",
        "postgresql+psycopg://tester:synthetic@127.0.0.1:6543/visionq_t4_test",
    )
    engine = database()
    try:
        assert engine.url.host == "127.0.0.1"
        assert engine.url.port == 6543
        assert engine.url.database == "visionq_t4_test"
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "value",
    ["", "sqlite:///test.db", "postgresql+psycopg://localhost"],
)
def test_invalid_override_is_rejected(monkeypatch, value):
    monkeypatch.setenv("VISIONQ_DATABASE_URL", value)
    with pytest.raises(ValueError):
        database()
