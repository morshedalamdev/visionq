"""Authoritative M4.T1 metric definitions and canonical serialization."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

METRIC_CATALOG_VERSION = "m4t1-v1"
QUERY_VERSION = "m4t1-v1"


class MetricDefinitionError(ValueError):
    pass


@dataclass(frozen=True)
class MetricDefinition:
    name: str
    description: str
    unit: str
    value_type: str
    numerator: str | None
    denominator: str | None
    aggregation: str
    source: str
    supports_class_filter: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "unit": self.unit,
            "value_type": self.value_type,
            "numerator": self.numerator,
            "denominator": self.denominator,
            "aggregation": self.aggregation,
            "source": self.source,
            "supports_class_filter": self.supports_class_filter,
        }


METRIC_CATALOG = {
    definition.name: definition
    for definition in (
        MetricDefinition(
            "batch_image_count",
            "Unique images in the immutable selected batch membership.",
            "images",
            "integer",
            None,
            None,
            "count distinct batch assets",
            "batch_items",
        ),
        MetricDefinition(
            "processed_image_count",
            "Batch images with a successful result in the selected inference run.",
            "images",
            "integer",
            None,
            "batch_image_count",
            "count distinct successful image results",
            "image_results",
        ),
        MetricDefinition(
            "failed_image_count",
            "Distinct batch images with a failed image result.",
            "images",
            "integer",
            None,
            "batch_image_count",
            "count distinct failed image results",
            "image_results",
        ),
        MetricDefinition(
            "pending_image_count",
            "Distinct batch images still pending in the selected run.",
            "images",
            "integer",
            None,
            "batch_image_count",
            "count distinct pending image results",
            "image_results",
        ),
        MetricDefinition(
            "running_image_count",
            "Distinct batch images actively running in the selected run.",
            "images",
            "integer",
            None,
            "batch_image_count",
            "count distinct running image results",
            "image_results",
        ),
        MetricDefinition(
            "predicted_box_count",
            "Persisted predictions at the recorded operating threshold.",
            "boxes",
            "integer",
            None,
            "processed_image_count",
            "count persisted detections in successful results",
            "detections",
            True,
        ),
        MetricDefinition(
            "images_with_prediction",
            "Successful images with at least one persisted qualifying prediction.",
            "images",
            "integer",
            None,
            "processed_image_count",
            "count distinct successful assets with detections",
            "detections",
            True,
        ),
        MetricDefinition(
            "prediction_image_ratio",
            "Share of successful images with a qualifying prediction.",
            "fraction",
            "number",
            "images_with_prediction",
            "processed_image_count",
            "numerator divided by denominator",
            "derived",
            True,
        ),
        MetricDefinition(
            "boxes_per_processed_image",
            "Qualifying boxes per successful processed image.",
            "boxes/image",
            "number",
            "predicted_box_count",
            "processed_image_count",
            "numerator divided by denominator",
            "derived",
            True,
        ),
        MetricDefinition(
            "processing_coverage",
            "Share of immutable batch members with a successful image result.",
            "fraction",
            "number",
            "processed_image_count",
            "batch_image_count",
            "numerator divided by denominator",
            "derived",
        ),
        MetricDefinition(
            "quarantined_image_count",
            "Distinct assets excluded by unresolved error findings in the dataset version.",
            "images",
            "integer",
            None,
            None,
            "count distinct error-quality assets",
            "quality_issues",
        ),
        MetricDefinition(
            "quality_issue_count",
            "Quality findings captured for the selected dataset version.",
            "findings",
            "integer",
            None,
            None,
            "count quality findings",
            "quality_issues",
        ),
    )
}


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def content_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def definition_sha256(name: str) -> str:
    try:
        definition = METRIC_CATALOG[name]
    except KeyError:
        raise MetricDefinitionError(f"unknown metric: {name}") from None
    return content_sha256({"version": METRIC_CATALOG_VERSION, **definition.as_dict()})


def metric_catalogue() -> dict[str, Any]:
    return {
        "version": METRIC_CATALOG_VERSION,
        "metrics": [
            {
                **definition.as_dict(),
                "definition_sha256": definition_sha256(name),
            }
            for name, definition in METRIC_CATALOG.items()
        ],
    }


def normalize_metric_names(names: list[str] | None) -> tuple[str, ...]:
    selected = tuple(names or METRIC_CATALOG)
    if not selected:
        raise MetricDefinitionError("at least one metric is required")
    unknown = sorted(set(selected) - set(METRIC_CATALOG))
    if unknown:
        raise MetricDefinitionError(f"unknown metrics: {', '.join(unknown)}")
    if len(set(selected)) != len(selected):
        raise MetricDefinitionError("metric names must be unique")
    return tuple(name for name in METRIC_CATALOG if name in selected)


@dataclass(frozen=True)
class AnalyticsScope:
    dataset_version_id: str
    batch_id: str
    inference_run_id: str
    class_id: int | None = None

    @classmethod
    def from_values(
        cls,
        dataset_version_id: str,
        batch_id: str,
        inference_run_id: str,
        class_id: int | None = None,
    ) -> AnalyticsScope:
        for label, value in (
            ("dataset_version_id", dataset_version_id),
            ("batch_id", batch_id),
            ("inference_run_id", inference_run_id),
        ):
            try:
                UUID(str(value))
            except (AttributeError, TypeError, ValueError):
                raise MetricDefinitionError(f"{label} must be a UUID") from None
        if class_id is not None and (
            isinstance(class_id, bool) or not 0 <= class_id < 6
        ):
            raise MetricDefinitionError("class_id must be between 0 and 5")
        return cls(
            str(dataset_version_id),
            str(batch_id),
            str(inference_run_id),
            class_id,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset_version_id": self.dataset_version_id,
            "batch_id": self.batch_id,
            "inference_run_id": self.inference_run_id,
            "class_id": self.class_id,
        }
