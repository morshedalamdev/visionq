"""Real-size quality evidence must remain complete and finitely bounded."""

import pytest

from analytics.metrics import AnalyticsScope
from analytics.service import (
    MAX_QUALITY_FINDINGS,
    SnapshotContextError,
    _quality_evidence,
)


class Rows:
    def __init__(self, count):
        self.count = count

    def execute(self, statement, params):
        self.limit = params["fetch_limit"]
        return self

    def mappings(self):
        return self

    def all(self):
        return [
            {
                "issue_id": str(i),
                "asset_id": None,
                "rule_id": "fixture",
                "severity": "warning",
                "details": {},
            }
            for i in range(min(self.count, self.limit))
        ]


SCOPE = AnalyticsScope.from_values(
    "11111111-1111-4111-8111-111111111111",
    "22222222-2222-4222-8222-222222222222",
    "33333333-3333-4333-8333-333333333333",
)


def test_released_catalog_sized_evidence_is_complete():
    result = _quality_evidence(Rows(3779), SCOPE)
    assert result["finding_count"] == len(result["findings"]) == 3779
    assert result["counts_by_rule_and_severity"]["fixture"]["warning"] == 3779
    assert result["truncated"] is False


def test_oversized_evidence_is_rejected_not_truncated():
    with pytest.raises(SnapshotContextError, match="exceed"):
        _quality_evidence(Rows(MAX_QUALITY_FINDINGS + 1), SCOPE)
