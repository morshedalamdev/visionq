"""Snapshot-only tool behavior for the VisionQ MCP server."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError

from analytics.metrics import normalize_metric_names
from analytics.service import (
    CONTEXT_FORMAT,
    AnalyticsCompatibilityError,
    SnapshotIntegrityError,
    compare_payloads,
    read_snapshot,
)
from mcp_server.schemas import (
    BatchMetricsResponse,
    CompareBatchesResponse,
    QualityReportResponse,
    RunProvenanceResponse,
    SearchDocumentsResponse,
)
from retrieval.embeddings import EmbeddingBackend, EmbeddingServiceError
from retrieval.service import (
    CorpusConflict,
    EmbeddingCompatibilityError,
    search,
)


class MCPToolError(ValueError):
    pass


@dataclass(frozen=True)
class MCPContext:
    engine: Any
    embedding_backend: EmbeddingBackend
    query_timeout_ms: int


def _uuid(value: UUID | str, field: str) -> str:
    try:
        return str(UUID(str(value)))
    except (AttributeError, TypeError, ValueError):
        raise MCPToolError(f"{field} must be a UUID") from None


class MCPToolService:
    def __init__(self, context: MCPContext):
        self.context = context

    def _snapshot(self, snapshot_id: UUID | str) -> dict:
        try:
            return read_snapshot(
                self.context.engine,
                _uuid(snapshot_id, "snapshot_id"),
                read_only=True,
                statement_timeout_ms=self.context.query_timeout_ms,
            )
        except (SQLAlchemyError, SnapshotIntegrityError) as exc:
            raise MCPToolError("snapshot storage is unavailable or corrupt") from exc
        except ValueError as exc:
            raise MCPToolError(str(exc)) from exc

    @staticmethod
    def _scope_items(snapshot: dict) -> list[dict]:
        payload = snapshot["payload"]
        if payload.get("format") == CONTEXT_FORMAT:
            scope_set = payload.get("scope_set")
            if not isinstance(scope_set, list) or not scope_set:
                raise MCPToolError("snapshot contains no authorized scopes")
            return scope_set
        if payload.get("format") == "visionq-analytics-evidence-v1":
            return [{"role": "primary", "evidence": payload}]
        raise MCPToolError("unsupported analytics snapshot format")

    def _scope(
        self,
        snapshot: dict,
        *,
        batch_id: UUID | str | None = None,
        inference_run_id: UUID | str | None = None,
        role: str | None = None,
    ) -> dict:
        batch = _uuid(batch_id, "batch_id") if batch_id is not None else None
        run = (
            _uuid(inference_run_id, "inference_run_id")
            if inference_run_id is not None
            else None
        )
        matches = []
        for item in self._scope_items(snapshot):
            scope = item["evidence"].get("scope", {})
            if role is not None and item.get("role") != role:
                continue
            if batch is not None and str(scope.get("batch_id")) != batch:
                continue
            if run is not None and str(scope.get("inference_run_id")) != run:
                continue
            matches.append(item)
        if len(matches) != 1:
            raise MCPToolError(
                "requested scope is not uniquely authorized by the snapshot"
            )
        return matches[0]

    @staticmethod
    def _metrics(evidence: dict, names: list[str] | None) -> list[dict]:
        try:
            selected = normalize_metric_names(names)
        except ValueError as exc:
            raise MCPToolError(str(exc)) from exc
        metric_map = {item["metric_name"]: item for item in evidence["metrics"]}
        missing = [name for name in selected if name not in metric_map]
        if missing:
            raise MCPToolError(f"metric is absent from captured snapshot: {missing[0]}")
        return [metric_map[name] for name in selected]

    def batch_metrics(
        self,
        snapshot_id: UUID,
        batch_id: UUID,
        inference_run_id: UUID,
        metric_names: list[str],
        class_id: int | None,
    ) -> BatchMetricsResponse:
        snapshot = self._snapshot(snapshot_id)
        evidence = self._scope(
            snapshot,
            batch_id=batch_id,
            inference_run_id=inference_run_id,
        )["evidence"]
        captured_class = evidence["scope"].get("class_id")
        if class_id is not None and class_id != captured_class:
            raise MCPToolError(
                "class filter is not authorized by the captured snapshot"
            )
        return BatchMetricsResponse(
            snapshot_id=str(snapshot["id"]),
            snapshot_sha256=snapshot["payload_sha256"],
            scope=evidence["scope"],
            coverage=evidence["coverage"],
            provenance=evidence["provenance"],
            metrics=self._metrics(evidence, metric_names),
        )

    def compare_batches(
        self,
        snapshot_id: UUID,
        left_batch_id: UUID,
        left_inference_run_id: UUID,
        right_batch_id: UUID,
        right_inference_run_id: UUID,
        metric_names: list[str],
    ) -> CompareBatchesResponse:
        snapshot = self._snapshot(snapshot_id)
        if snapshot["payload"].get("format") != CONTEXT_FORMAT:
            raise MCPToolError(
                "comparison requires an evidence-v2 multi-scope snapshot"
            )
        left = self._scope(
            snapshot,
            batch_id=left_batch_id,
            inference_run_id=left_inference_run_id,
            role="left",
        )["evidence"]
        right = self._scope(
            snapshot,
            batch_id=right_batch_id,
            inference_run_id=right_inference_run_id,
            role="right",
        )["evidence"]
        try:
            comparison = compare_payloads(left, right, metric_names)
        except (AnalyticsCompatibilityError, ValueError) as exc:
            raise MCPToolError(f"incompatible captured comparison: {exc}") from exc
        return CompareBatchesResponse(
            snapshot_id=str(snapshot["id"]),
            snapshot_sha256=snapshot["payload_sha256"],
            query_version=comparison["query_version"],
            metric_catalog_version=comparison["metric_catalog_version"],
            metrics=comparison["metrics"],
        )

    def quality_report(
        self,
        snapshot_id: UUID,
        dataset_version_id: UUID,
        batch_id: UUID | None,
    ) -> QualityReportResponse:
        snapshot = self._snapshot(snapshot_id)
        if snapshot["payload"].get("format") != CONTEXT_FORMAT:
            raise MCPToolError(
                "quality findings require an evidence-v2 context snapshot"
            )
        dataset = _uuid(dataset_version_id, "dataset_version_id")
        selected = [
            item
            for item in self._scope_items(snapshot)
            if item["evidence"]["scope"]["dataset_version_id"] == dataset
            and (
                batch_id is None
                or item["evidence"]["scope"]["batch_id"] == _uuid(batch_id, "batch_id")
            )
        ]
        if not selected:
            raise MCPToolError(
                "requested quality scope is not uniquely authorized by the snapshot"
            )
        item = selected[0]["evidence"]
        expected_quality = item.get("quality")
        if any(
            candidate["evidence"].get("quality") != expected_quality
            for candidate in selected[1:]
        ):
            raise MCPToolError(
                "captured quality evidence differs across authorized scopes"
            )
        quality = item.get("quality")
        if not isinstance(quality, dict):
            raise MCPToolError("captured quality evidence is unavailable")
        return QualityReportResponse(
            snapshot_id=str(snapshot["id"]),
            snapshot_sha256=snapshot["payload_sha256"],
            dataset_version_id=dataset,
            batch_id=item["scope"]["batch_id"],
            finding_count=quality["finding_count"],
            findings=quality["findings"],
            counts_by_rule_and_severity=quality["counts_by_rule_and_severity"],
            quarantined_asset_ids=quality["quarantined_asset_ids"],
            quarantined_image_count=quality["quarantined_image_count"],
            truncated=quality["truncated"],
            coverage=item["coverage"],
        )

    def run_provenance(
        self,
        snapshot_id: UUID,
        inference_run_id: UUID,
    ) -> RunProvenanceResponse:
        snapshot = self._snapshot(snapshot_id)
        item = self._scope(
            snapshot,
            inference_run_id=inference_run_id,
        )["evidence"]
        provenance = item["provenance"]
        links = item.get("evaluation_links")
        if links is None:
            links = {
                "available": False,
                "items": [],
                "reason": "not captured by the historical snapshot format",
            }
        return RunProvenanceResponse(
            snapshot_id=str(snapshot["id"]),
            snapshot_sha256=snapshot["payload_sha256"],
            scope=item["scope"],
            coverage=item["coverage"],
            dataset=provenance["dataset"],
            batch=provenance["batch"],
            model=provenance["model"],
            run=provenance["run"],
            evaluation_links=links,
        )

    def search_documents(
        self,
        snapshot_id: UUID,
        query: str,
        corpus_version_id: UUID,
        retrieval_index_id: UUID,
        top_k: int = 4,
    ) -> SearchDocumentsResponse:
        snapshot = self._snapshot(snapshot_id)
        pin = snapshot["payload"].get("pinned_retrieval")
        if snapshot["payload"].get("format") != CONTEXT_FORMAT or pin is None:
            raise MCPToolError(
                "search requires an evidence-v2 snapshot with a pinned index"
            )
        corpus = _uuid(corpus_version_id, "corpus_version_id")
        index = _uuid(retrieval_index_id, "retrieval_index_id")
        if (
            pin["corpus_version_id"] != corpus
            or pin["retrieval_index_id"] != index
            or str(snapshot.get("pinned_corpus_version_id")) != corpus
            or str(snapshot.get("pinned_retrieval_index_id")) != index
        ):
            raise MCPToolError("requested corpus/index is not pinned by the snapshot")
        try:
            result = search(
                self.context.engine,
                self.context.embedding_backend,
                corpus,
                index,
                query,
                min(top_k, 4),
                read_only=True,
                statement_timeout_ms=self.context.query_timeout_ms,
            )
        except EmbeddingServiceError as exc:
            raise MCPToolError(str(exc)) from exc
        except (CorpusConflict, EmbeddingCompatibilityError, ValueError) as exc:
            raise MCPToolError(str(exc)) from exc
        except SQLAlchemyError as exc:
            raise MCPToolError("retrieval storage is unavailable") from exc
        return SearchDocumentsResponse(
            snapshot_id=str(snapshot["id"]),
            snapshot_sha256=snapshot["payload_sha256"],
            corpus_version_id=corpus,
            index_id=index,
            query=query,
            top_k=min(top_k, 4),
            score_semantics=result["score_semantics"],
            evidence_kind=result["evidence_kind"],
            results=result["results"],
        )
