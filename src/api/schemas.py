"""Typed analytics API request contracts."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from analytics.metrics import normalize_metric_names


class AnalyticsScopeRequest(BaseModel):
    dataset_version_id: UUID
    batch_id: UUID
    inference_run_id: UUID
    class_id: Annotated[int, Field(ge=0, le=5)] | None = None


class SnapshotCreateRequest(AnalyticsScopeRequest):
    metric_names: list[str] | None = None

    @field_validator("metric_names")
    @classmethod
    def valid_metrics(cls, value: list[str] | None) -> list[str] | None:
        if value is not None:
            return list(normalize_metric_names(value))
        return value


class ScopeComparisonRequest(BaseModel):
    left: AnalyticsScopeRequest
    right: AnalyticsScopeRequest
    metric_names: list[str] | None = None

    @field_validator("metric_names")
    @classmethod
    def valid_metrics(cls, value: list[str] | None) -> list[str] | None:
        if value is not None:
            return list(normalize_metric_names(value))
        return value


class SnapshotComparisonRequest(BaseModel):
    left_snapshot_id: UUID
    right_snapshot_id: UUID
    metric_names: list[str] | None = None

    @field_validator("metric_names")
    @classmethod
    def valid_metrics(cls, value: list[str] | None) -> list[str] | None:
        if value is not None:
            return list(normalize_metric_names(value))
        return value
