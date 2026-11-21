"""Canonical VisionQ analytics contracts."""

from analytics.metrics import (
    METRIC_CATALOG,
    METRIC_CATALOG_VERSION,
    AnalyticsScope,
    metric_catalogue,
)
from analytics.service import (
    AnalyticsCompatibilityError,
    AnalyticsError,
    AnalyticsScopeError,
    SnapshotPersistenceError,
    capture_snapshot,
    compare_scopes,
    compare_snapshots,
    read_snapshot,
)

__all__ = [
    "METRIC_CATALOG",
    "METRIC_CATALOG_VERSION",
    "AnalyticsCompatibilityError",
    "AnalyticsError",
    "AnalyticsScope",
    "AnalyticsScopeError",
    "SnapshotPersistenceError",
    "capture_snapshot",
    "compare_scopes",
    "compare_snapshots",
    "metric_catalogue",
    "read_snapshot",
]
