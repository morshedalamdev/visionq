"""Typed M4.T4 dashboard and upload API contracts."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

EvidenceKind = Literal["synthetic", "released"]


class Page(BaseModel):
    limit: int
    offset: int
    has_more: bool


class DatasetListItem(BaseModel):
    id: str
    dataset_name: str
    version: int
    evidence_kind: EvidenceKind
    release_manifest_sha256: str
    created_at: str
    asset_count: int
    batch_count: int
    latest_ingestion_status: str | None
    error_quality_issue_count: int
    warning_quality_issue_count: int


class DatasetListResponse(BaseModel):
    items: list[DatasetListItem]
    page: Page


class DatasetSummaryResponse(BaseModel):
    dataset: DatasetListItem
    splits: dict[str, int]
    quality_by_rule: list[dict[str, Any]]


class BatchItem(BaseModel):
    id: str
    dataset_version_id: str
    kind: str
    split: str | None
    member_count: int
    membership_sha256: str
    created_at: str
    latest_run_id: str | None
    latest_run_status: str | None


class BatchListResponse(BaseModel):
    items: list[BatchItem]
    page: Page


class RunItem(BaseModel):
    id: str
    dataset_version_id: str
    batch_id: str
    model_id: str
    status: str
    evidence_kind: str
    architecture: str
    model_sha256: str
    expected_items: int
    succeeded_items: int
    failed_items: int
    pending_items: int
    running_items: int
    started_at: str | None
    finished_at: str | None
    created_at: str
    config: dict[str, Any]


class RunListResponse(BaseModel):
    items: list[RunItem]
    page: Page


class RunDetailResponse(RunItem):
    batch_kind: str
    batch_split: str | None
    membership_sha256: str
    classes: list[str]
    config_sha256: str
    model_config_sha256: str
    inference_config: dict[str, Any]
    dataset_name: str
    dataset_release: int
    dataset_evidence_kind: str


class Detection(BaseModel):
    ordinal: int
    class_id: int
    class_name: str
    confidence: float
    box_xmin: float
    box_ymin: float
    box_xmax: float
    box_ymax: float


class RunImageResult(BaseModel):
    asset_id: str
    status: str
    image_sha256: str
    width: int
    height: int
    detection_count: int | None
    raw_prediction_count: int | None
    latency_ms: float | None
    attempts: int
    last_error: str | None
    image_url: str
    overlay_sha256: str | None
    overlay_url: str | None
    detections: list[Detection]


class RunResultsResponse(BaseModel):
    items: list[RunImageResult]
    page: Page


class UploadRequestResponse(BaseModel):
    id: str
    original_filename: str
    content_sha256: str
    byte_count: int
    media_type: Literal["image/png", "image/jpeg"]
    width: int
    height: int
    artifact_url: str
    status: Literal["pending", "ready", "failed"]
    inference_state: Literal["not_started", "pending_registration", "unavailable"]
    dataset_version_id: str | None
    batch_id: str | None
    failure_reason: str | None
    created_at: str
    updated_at: str


class UploadListResponse(BaseModel):
    items: list[UploadRequestResponse]
    page: Page


class AgentFixtureResponse(BaseModel):
    id: str
    evidence_kind: Literal["development-fixture"]
    question: str
    status: Literal["answered", "partial", "clarification", "abstained", "error"]
    answer: str
    numeric_claims: list[dict[str, Any]]
    citations: list[dict[str, Any]]
    verification_status: str
    tool_trace: list[dict[str, Any]]
