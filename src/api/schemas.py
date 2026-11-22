"""Typed analytics API request contracts."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

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


class SnapshotScopeRequest(AnalyticsScopeRequest):
    role: Literal["primary", "left", "right"]


class ContextSnapshotCreateRequest(BaseModel):
    scopes: list[SnapshotScopeRequest] = Field(min_length=1, max_length=3)
    metric_names: list[str] | None = None
    pinned_corpus_version_id: UUID | None = None
    pinned_retrieval_index_id: UUID | None = None

    @field_validator("metric_names")
    @classmethod
    def valid_metrics(cls, value: list[str] | None) -> list[str] | None:
        if value is not None:
            return list(normalize_metric_names(value))
        return value

    @model_validator(mode="after")
    def valid_scope_set(self) -> ContextSnapshotCreateRequest:
        roles = [scope.role for scope in self.scopes]
        if len(set(roles)) != len(roles):
            raise ValueError("scope roles must be unique")
        if ("left" in roles) != ("right" in roles):
            raise ValueError("comparison snapshots require left and right scopes")
        if (self.pinned_corpus_version_id is None) != (
            self.pinned_retrieval_index_id is None
        ):
            raise ValueError(
                "corpus version and retrieval index must be pinned together"
            )
        return self


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
