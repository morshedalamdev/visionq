from __future__ import annotations

from copy import deepcopy

import pytest

from analytics.metrics import (
    METRIC_CATALOG,
    METRIC_CATALOG_VERSION,
    AnalyticsScope,
    MetricDefinitionError,
    content_sha256,
    metric_catalogue,
)
from analytics.service import AnalyticsCompatibilityError, compare_payloads


def metric(name, value, denominator_name=None, denominator_value=None):
    definition = METRIC_CATALOG[name]
    return {
        "metric_name": name,
        "value": value,
        "unit": definition.unit,
        "definition_sha256": "definition-" + name,
        "denominator_name": denominator_name,
        "denominator_value": denominator_value,
        "evidence_status": "available" if value is not None else "unavailable",
    }


def payload(run_id, values, *, release="release-a", class_id=None):
    return {
        "query_version": "m4t1-v1",
        "metric_catalog_version": METRIC_CATALOG_VERSION,
        "scope": {
            "dataset_version_id": "00000000-0000-0000-0000-000000000001",
            "batch_id": "00000000-0000-0000-0000-000000000002",
            "inference_run_id": run_id,
            "model_id": "00000000-0000-0000-0000-000000000003",
            "class_id": class_id,
        },
        "provenance": {
            "dataset": {
                "evidence_kind": "synthetic",
                "release_manifest_sha256": release,
            },
            "model": {
                "evidence_kind": "synthetic",
                "architecture": "yolo11n",
                "class_map_version": "neu-det-v1",
                "checkpoint_sha256": "checkpoint",
                "inference_config_sha256": "config",
                "inference_config": {"confidence_threshold": 0.07},
            },
        },
        "metrics": [
            metric(name, value, *denominator)
            for name, (value, denominator) in values.items()
        ],
    }


def test_metric_catalogue_is_complete_and_definition_addresses_are_stable():
    catalogue = metric_catalogue()
    names = [item["name"] for item in catalogue["metrics"]]

    assert catalogue["version"] == METRIC_CATALOG_VERSION
    assert names == list(METRIC_CATALOG)
    assert len(names) == 12
    assert {
        "processed_image_count",
        "prediction_image_ratio",
        "quarantined_image_count",
        "quality_issue_count",
    } <= set(names)
    assert metric_catalogue() == catalogue
    assert all(len(item["definition_sha256"]) == 64 for item in catalogue["metrics"])


def test_canonical_hash_ignores_mapping_insertion_order():
    first = {"a": 1, "b": {"x": 2, "y": 3}}
    second = {"b": {"y": 3, "x": 2}, "a": 1}

    assert content_sha256(first) == content_sha256(second)
    assert content_sha256(first) != content_sha256({**first, "a": 2})


def test_scope_validation_rejects_bad_ids_and_class():
    with pytest.raises(MetricDefinitionError, match="dataset_version_id"):
        AnalyticsScope.from_values("not-a-uuid", "b", "c")
    with pytest.raises(MetricDefinitionError, match="class_id"):
        AnalyticsScope.from_values(
            "00000000-0000-0000-0000-000000000001",
            "00000000-0000-0000-0000-000000000002",
            "00000000-0000-0000-0000-000000000003",
            6,
        )


def test_comparison_reports_absolute_relative_and_percentage_point_deltas():
    values = {
        "prediction_image_ratio": (0.25, ("processed_image_count", 8)),
        "predicted_box_count": (4, ("processed_image_count", 8)),
    }
    left = payload("left", values)
    right_values = {
        "prediction_image_ratio": (0.5, ("processed_image_count", 10)),
        "predicted_box_count": (10, ("processed_image_count", 10)),
    }
    right = payload("right", right_values)

    comparison = compare_payloads(left, right, list(values))
    compared = {item["metric_name"]: item for item in comparison["metrics"]}
    ratio = compared["prediction_image_ratio"]
    boxes = compared["predicted_box_count"]

    assert ratio["absolute_delta"] == 0.25
    assert ratio["relative_delta"] == 1
    assert ratio["percentage_point_delta"] == 25
    assert boxes["absolute_delta"] == 6
    assert boxes["relative_delta"] == 1.5
    assert boxes["percentage_point_delta"] is None


def test_zero_left_value_has_explicit_relative_reason():
    values = {
        "predicted_box_count": (0, ("processed_image_count", 2)),
    }
    left = payload("left", values)
    right = payload(
        "right",
        {"predicted_box_count": (2, ("processed_image_count", 2))},
    )

    result = compare_payloads(left, right, list(values))["metrics"][0]

    assert result["absolute_delta"] == 2
    assert result["relative_delta"] is None
    assert result["relative_delta_reason"] == "zero_left_value"


def test_unavailable_values_are_not_compared_as_zero():
    values = {"prediction_image_ratio": (None, ("processed_image_count", 0))}
    result = compare_payloads(
        payload("left", values),
        payload("right", values),
        list(values),
    )["metrics"][0]

    assert result["absolute_delta"] is None
    assert result["relative_delta"] is None
    assert result["relative_delta_reason"] == "one or both values are unavailable"


def test_comparison_rejects_changed_dataset_class_or_model_contract():
    values = {"predicted_box_count": (1, ("processed_image_count", 1))}
    left = payload("left", values)
    mismatches = []

    right = deepcopy(left)
    right["scope"]["inference_run_id"] = "right"
    right["scope"]["dataset_version_id"] = "other-version"
    mismatches.append(right)

    right = deepcopy(left)
    right["scope"]["inference_run_id"] = "right"
    right["scope"]["class_id"] = 1
    mismatches.append(right)

    right = deepcopy(left)
    right["scope"]["inference_run_id"] = "right"
    right["provenance"]["model"]["checkpoint_sha256"] = "other-checkpoint"
    mismatches.append(right)

    for right in mismatches:
        with pytest.raises(AnalyticsCompatibilityError, match="incompatible"):
            compare_payloads(left, right, list(values))
