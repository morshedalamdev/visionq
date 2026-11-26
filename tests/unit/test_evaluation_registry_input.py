"""Registration fails closed before database access on unverified artifacts."""

import pytest

from worker.evaluation_registry import register_evidence


def test_bad_sealed_input_never_opens_database(tmp_path):
    class Forbidden:
        def connect(self):
            raise AssertionError("database must not be opened")

    with pytest.raises(FileNotFoundError):
        register_evidence(
            Forbidden(),
            tmp_path,
            "unused",
            tmp_path,
            "a" * 64,
            tmp_path,
            "b" * 64,
            tmp_path,
            "c" * 64,
        )
