"""Strongly typed MCP tool inputs and outputs."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class MetricItem(BaseModel):
    metric_name: str
    value: int | float | None
    unit: str
    value_type: str
    definition_version: str
    definition_sha256: str
    denominator_name: str | None
    denominator_value: int | None
    filters: dict[str, int | float | str | None]
    evidence_status: str
    reason: str | None


class Coverage(BaseModel):
    batch_member_count: int
    expected_result_count: int
    observed_result_count: int
    processed_image_count: int
    failed_image_count: int
    pending_image_count: int
    running_image_count: int
    run_status: str
    evidence_status: str


class BatchMetricsResponse(BaseModel):
    snapshot_id: str
    snapshot_sha256: str
    scope: dict[str, str | int | None]
    coverage: Coverage
    provenance: dict
    metrics: list[MetricItem]


class ComparisonSide(BaseModel):
    scope: dict[str, str | int | None]
    value: int | float | None
    evidence_status: str
    denominator_name: str | None
    denominator_value: int | None


class ComparisonMetric(BaseModel):
    metric_name: str
    unit: str
    definition_sha256: str
    left: ComparisonSide
    right: ComparisonSide
    absolute_delta: int | float | None
    relative_delta: float | None
    relative_delta_reason: str | None
    percentage_point_delta: float | None


class CompareBatchesResponse(BaseModel):
    snapshot_id: str
    snapshot_sha256: str
    query_version: str
    metric_catalog_version: str
    compatibility_status: Literal["compatible"] = "compatible"
    metrics: list[ComparisonMetric]


class QualityFinding(BaseModel):
    issue_id: str
    asset_id: str | None
    rule_id: str
    severity: Literal["warning", "error"]
    details: dict


class QualityReportResponse(BaseModel):
    snapshot_id: str
    snapshot_sha256: str
    dataset_version_id: str
    batch_id: str
    finding_count: int
    findings: list[QualityFinding]
    counts_by_rule_and_severity: dict[str, dict[str, int]]
    quarantined_asset_ids: list[str]
    quarantined_image_count: int
    truncated: bool
    coverage: Coverage


class RunProvenanceResponse(BaseModel):
    snapshot_id: str
    snapshot_sha256: str
    scope: dict[str, str | int | None]
    coverage: Coverage
    dataset: dict
    batch: dict
    model: dict
    run: dict
    evaluation_links: dict


class RetrievalCitation(BaseModel):
    corpus_version_id: str
    index_id: str
    chunk_id: str
    document_id: str
    document_key: str
    document_version: str
    title: str
    source_location: str
    section_title: str
    text: str
    start_character: int
    end_character: int
    document_sha256: str
    chunk_sha256: str
    score: float
    score_semantics: Literal["cosine_similarity"]
    embedding_backend: str
    embedding_model: str
    embedding_revision: str
    corpus_evidence_kind: str


class SearchDocumentsResponse(BaseModel):
    snapshot_id: str
    snapshot_sha256: str
    corpus_version_id: str
    index_id: str
    query: str
    top_k: int
    score_semantics: Literal["cosine_similarity"]
    evidence_kind: str
    results: list[RetrievalCitation]
