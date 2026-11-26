"""Scoped PostgreSQL analytics, immutable snapshots and deterministic comparisons."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Callable
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError

from analytics.metrics import (
    METRIC_CATALOG,
    METRIC_CATALOG_VERSION,
    QUERY_VERSION,
    AnalyticsScope,
    canonical_bytes,
    content_sha256,
    definition_sha256,
    normalize_metric_names,
)
from worker.evaluation_registry import scoped_evidence

SnapshotHook = Callable[[str], None]
CONTEXT_FORMAT = "visionq-question-snapshot-v2"
CONTEXT_ROLES = frozenset({"primary", "left", "right"})
MAX_CONTEXT_SCOPES = 3
# A released 1,797-image catalog currently has 3,779 retained findings.
# Keep complete immutable evidence with a finite bound; never silently truncate.
MAX_QUALITY_FINDINGS = 5_000
MAX_CONTEXT_PAYLOAD_BYTES = 8 * 1024 * 1024


class AnalyticsError(RuntimeError):
    pass


class AnalyticsScopeError(AnalyticsError, ValueError):
    pass


class AnalyticsCompatibilityError(AnalyticsError, ValueError):
    pass


class SnapshotPersistenceError(AnalyticsError):
    pass


class SnapshotIntegrityError(AnalyticsError):
    pass


class SnapshotContextError(AnalyticsError, ValueError):
    pass


def _load_scope(connection, scope: AnalyticsScope) -> dict[str, Any]:
    row = (
        connection.execute(
            text("""
                SELECT
                    dv.id AS dataset_version_id,
                    dv.dataset_name,
                    dv.version AS dataset_release,
                    dv.evidence_kind,
                    dv.release_manifest_sha256,
                    dv.source_manifest_sha256,
                    b.id AS batch_id,
                    b.kind AS batch_kind,
                    b.split AS batch_split,
                    b.membership_sha256,
                    b.member_count,
                    ir.id AS inference_run_id,
                    ir.status AS run_status,
                    ir.config_sha256 AS run_config_sha256,
                    ir.config AS run_config,
                    ir.expected_items,
                    ir.started_at,
                    ir.finished_at,
                    m.id AS model_id,
                    m.evidence_kind AS model_evidence_kind,
                    m.architecture,
                    m.class_map_version,
                    m.classes,
                    m.checkpoint_sha256,
                    m.training_manifest_sha256,
                    m.selection_manifest_sha256,
                    m.inference_config_sha256,
                    m.inference_config
                FROM inference_runs AS ir
                JOIN batches AS b
                  ON b.id = ir.batch_id
                 AND b.dataset_version_id = ir.dataset_version_id
                JOIN dataset_versions AS dv
                  ON dv.id = ir.dataset_version_id
                JOIN models AS m
                  ON m.id = ir.model_id
                 AND m.dataset_version_id = ir.dataset_version_id
                WHERE ir.id = CAST(:inference_run_id AS uuid)
                  AND ir.dataset_version_id = CAST(:dataset_version_id AS uuid)
                  AND ir.batch_id = CAST(:batch_id AS uuid)
            """),
            scope.as_dict(),
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise AnalyticsScopeError(
            "inference run does not match the requested dataset version and batch"
        )
    return _plain(dict(row))


def _counts(connection, scope: AnalyticsScope) -> dict[str, int]:
    row = (
        connection.execute(
            text("""
                WITH result_counts AS (
                    SELECT
                        count(*) FILTER (WHERE status = 'succeeded') AS processed,
                        count(*) FILTER (WHERE status = 'failed') AS failed,
                        count(*) FILTER (WHERE status = 'pending') AS pending,
                        count(*) FILTER (WHERE status = 'running') AS running,
                        count(*) AS observed
                    FROM image_results
                    WHERE run_id = CAST(:inference_run_id AS uuid)
                      AND dataset_version_id = CAST(:dataset_version_id AS uuid)
                      AND batch_id = CAST(:batch_id AS uuid)
                ),
                membership AS (
                    SELECT count(DISTINCT asset_id) AS member_count
                    FROM batch_items
                    WHERE batch_id = CAST(:batch_id AS uuid)
                      AND dataset_version_id = CAST(:dataset_version_id AS uuid)
                )
                SELECT
                    membership.member_count,
                    result_counts.observed,
                    result_counts.processed,
                    result_counts.failed,
                    result_counts.pending,
                    result_counts.running
                FROM membership
                CROSS JOIN result_counts
            """),
            scope.as_dict(),
        )
        .mappings()
        .one()
    )
    return {key: int(value) for key, value in row.items()}


def _prediction_counts(connection, scope: AnalyticsScope) -> dict[str, int]:
    row = (
        connection.execute(
            text("""
                SELECT
                    count(d.ordinal) AS boxes,
                    count(DISTINCT d.asset_id) AS images
                FROM image_results AS ir
                JOIN detections AS d
                  ON d.run_id = ir.run_id
                 AND d.asset_id = ir.asset_id
                WHERE ir.run_id = CAST(:inference_run_id AS uuid)
                  AND ir.dataset_version_id = CAST(:dataset_version_id AS uuid)
                  AND ir.batch_id = CAST(:batch_id AS uuid)
                  AND ir.status = 'succeeded'
                  AND (
                      CAST(:class_id AS integer) IS NULL
                      OR d.class_id = CAST(:class_id AS integer)
                  )
            """),
            scope.as_dict(),
        )
        .mappings()
        .one()
    )
    return {key: int(value) for key, value in row.items()}


def _quality_counts(connection, scope: AnalyticsScope) -> dict[str, int]:
    row = (
        connection.execute(
            text("""
                SELECT
                    count(*) AS issue_count,
                    count(DISTINCT asset_id)
                        FILTER (WHERE severity = 'error' AND asset_id IS NOT NULL)
                        AS quarantined
                FROM quality_issues
                WHERE dataset_version_id = CAST(:dataset_version_id AS uuid)
            """),
            scope.as_dict(),
        )
        .mappings()
        .one()
    )
    return {key: int(value) for key, value in row.items()}


def _status(run_status: str) -> str:
    if run_status == "succeeded":
        return "available"
    if run_status == "pending":
        return "pending"
    if run_status == "failed":
        return "failed"
    return "partial"


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def _metric_item(
    name: str,
    value: int | float | None,
    evidence_status: str,
    denominator_name: str | None,
    denominator_value: int | None,
    class_id: int | None,
    reason: str | None = None,
) -> dict[str, Any]:
    definition = METRIC_CATALOG[name]
    return {
        "metric_name": name,
        "value": value,
        "unit": definition.unit,
        "value_type": definition.value_type,
        "definition_version": METRIC_CATALOG_VERSION,
        "definition_sha256": definition_sha256(name),
        "denominator_name": denominator_name,
        "denominator_value": denominator_value,
        "filters": (
            {"class_id": class_id}
            if definition.supports_class_filter and class_id is not None
            else {}
        ),
        "evidence_status": evidence_status,
        "reason": reason,
    }


def _build_evidence(
    connection: Connection,
    scope: AnalyticsScope,
    metric_names: tuple[str, ...],
    hook: SnapshotHook | None = None,
) -> dict[str, Any]:
    loaded = _load_scope(connection, scope)
    if hook is not None:
        hook("after_scope_read")
    counts = _counts(connection, scope)
    predictions = _prediction_counts(connection, scope)
    quality = _quality_counts(connection, scope)

    if counts["member_count"] != loaded["member_count"]:
        raise SnapshotPersistenceError("batch membership count is inconsistent")
    if counts["observed"] > counts["member_count"]:
        raise SnapshotPersistenceError("run contains results outside batch membership")

    run_status = loaded["run_status"]
    run_evidence_status = _status(run_status)
    processed = counts["processed"]
    member_count = counts["member_count"]
    raw_values: dict[str, int | float | None] = {
        "batch_image_count": member_count,
        "processed_image_count": processed,
        "failed_image_count": counts["failed"],
        "pending_image_count": counts["pending"],
        "running_image_count": counts["running"],
        "predicted_box_count": predictions["boxes"] if processed else None,
        "images_with_prediction": predictions["images"] if processed else None,
        "prediction_image_ratio": _ratio(predictions["images"], processed),
        "boxes_per_processed_image": _ratio(predictions["boxes"], processed),
        "processing_coverage": _ratio(processed, member_count),
        "quarantined_image_count": quality["quarantined"],
        "quality_issue_count": quality["issue_count"],
    }
    denominators = {
        "processed_image_count": ("batch_image_count", member_count),
        "failed_image_count": ("batch_image_count", member_count),
        "pending_image_count": ("batch_image_count", member_count),
        "running_image_count": ("batch_image_count", member_count),
        "predicted_box_count": ("processed_image_count", processed),
        "images_with_prediction": ("processed_image_count", processed),
        "prediction_image_ratio": ("processed_image_count", processed),
        "boxes_per_processed_image": ("processed_image_count", processed),
        "processing_coverage": ("batch_image_count", member_count),
    }
    metrics = []
    for name in metric_names:
        value = raw_values[name]
        denominator = denominators.get(name, (None, None))
        definition = METRIC_CATALOG[name]
        evidence_status = (
            "available"
            if definition.source == "quality_issues"
            else run_evidence_status
        )
        reason = None
        if value is None:
            evidence_status = "unavailable"
            reason = (
                "no_batch_members"
                if name == "processing_coverage" and member_count == 0
                else "no_successful_images"
            )
        metrics.append(
            _metric_item(
                name,
                value,
                evidence_status,
                denominator[0],
                denominator[1],
                scope.class_id,
                reason,
            )
        )
    return {
        "format": "visionq-analytics-evidence-v1",
        "query_version": QUERY_VERSION,
        "metric_catalog_version": METRIC_CATALOG_VERSION,
        "scope": {
            "dataset_version_id": loaded["dataset_version_id"],
            "batch_id": loaded["batch_id"],
            "inference_run_id": loaded["inference_run_id"],
            "model_id": loaded["model_id"],
            "class_id": scope.class_id,
        },
        "filters": {
            "dataset_version": True,
            "batch": True,
            "inference_run": True,
            "class_id": scope.class_id,
        },
        "coverage": {
            "batch_member_count": member_count,
            "expected_result_count": loaded["expected_items"],
            "observed_result_count": counts["observed"],
            "processed_image_count": processed,
            "failed_image_count": counts["failed"],
            "pending_image_count": counts["pending"],
            "running_image_count": counts["running"],
            "run_status": run_status,
            "evidence_status": run_evidence_status,
        },
        "provenance": {
            "dataset": {
                "name": loaded["dataset_name"],
                "release": loaded["dataset_release"],
                "evidence_kind": loaded["evidence_kind"],
                "source_manifest_sha256": loaded["source_manifest_sha256"],
                "release_manifest_sha256": loaded["release_manifest_sha256"],
            },
            "batch": {
                "kind": loaded["batch_kind"],
                "split": loaded["batch_split"],
                "membership_sha256": loaded["membership_sha256"],
                "member_count": loaded["member_count"],
            },
            "model": {
                "evidence_kind": loaded["model_evidence_kind"],
                "architecture": loaded["architecture"],
                "class_map_version": loaded["class_map_version"],
                "classes": loaded["classes"],
                "checkpoint_sha256": loaded["checkpoint_sha256"],
                "training_manifest_sha256": loaded["training_manifest_sha256"],
                "selection_manifest_sha256": loaded["selection_manifest_sha256"],
                "inference_config_sha256": loaded["inference_config_sha256"],
                "inference_config": loaded["inference_config"],
            },
            "run": {
                "status": run_status,
                "config_sha256": loaded["run_config_sha256"],
                "config": loaded["run_config"],
                "expected_items": loaded["expected_items"],
                "started_at": loaded["started_at"],
                "finished_at": loaded["finished_at"],
            },
        },
        "evaluation_links": scoped_evidence(
            connection, scope.dataset_version_id, loaded["model_id"]
        ),
        "metrics": metrics,
    }


def _quality_evidence(
    connection: Connection,
    scope: AnalyticsScope,
) -> dict[str, Any]:
    rows = (
        connection.execute(
            text("""
                SELECT
                    CAST(id AS text) AS issue_id,
                    CAST(asset_id AS text) AS asset_id,
                    rule_id,
                    severity,
                    details
                FROM quality_issues
                WHERE dataset_version_id = CAST(:dataset_version_id AS uuid)
                ORDER BY rule_id, severity, id
                LIMIT :fetch_limit
            """),
            {**scope.as_dict(), "fetch_limit": MAX_QUALITY_FINDINGS + 1},
        )
        .mappings()
        .all()
    )
    if len(rows) > MAX_QUALITY_FINDINGS:
        raise SnapshotContextError(
            f"quality findings exceed snapshot bound of {MAX_QUALITY_FINDINGS}"
        )
    grouped: dict[str, dict[str, int]] = {}
    for row in rows:
        key = row["rule_id"]
        severity_counts = grouped.setdefault(key, {"warning": 0, "error": 0})
        severity_counts[row["severity"]] += 1
    findings = [_plain(dict(row)) for row in rows]
    quarantined = sorted(
        {
            row["asset_id"]
            for row in rows
            if row["severity"] == "error" and row["asset_id"] is not None
        }
    )
    return {
        "findings": findings,
        "finding_count": len(rows),
        "counts_by_rule_and_severity": grouped,
        "quarantined_asset_ids": quarantined,
        "quarantined_image_count": len(quarantined),
        "truncated": False,
        "max_findings": MAX_QUALITY_FINDINGS,
    }


def _retrieval_pin(
    connection: Connection,
    corpus_version_id: str | None,
    retrieval_index_id: str | None,
) -> dict[str, Any] | None:
    if (corpus_version_id is None) != (retrieval_index_id is None):
        raise SnapshotContextError(
            "corpus version and retrieval index must be pinned together"
        )
    if corpus_version_id is None:
        return None
    row = (
        connection.execute(
            text("""
                SELECT
                    CAST(cv.id AS text) AS corpus_version_id,
                    cv.corpus_name,
                    cv.version AS corpus_release,
                    cv.evidence_kind AS corpus_evidence_kind,
                    cv.manifest_sha256 AS corpus_manifest_sha256,
                    CAST(ri.id AS text) AS retrieval_index_id,
                    ri.profile_sha256,
                    ri.embedding_backend,
                    ri.embedding_model,
                    ri.embedding_revision,
                    ri.dimensions,
                    ri.pooling,
                    ri.normalization,
                    ri.query_prefix,
                    ri.document_prefix,
                    ri.status AS index_status
                FROM retrieval_indexes AS ri
                JOIN corpus_versions AS cv
                  ON cv.id = ri.corpus_version_id
                WHERE ri.id = CAST(:retrieval_index_id AS uuid)
                  AND ri.corpus_version_id = CAST(:corpus_version_id AS uuid)
                  AND ri.status = 'ready'
                  AND cv.status = 'ready'
            """),
            {
                "corpus_version_id": str(corpus_version_id),
                "retrieval_index_id": str(retrieval_index_id),
            },
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise SnapshotContextError("pinned corpus/index pair is missing or not ready")
    return _plain(dict(row))


def _plain(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_plain(item) for item in value]
    if isinstance(value, UUID):
        return str(value)
    return value


def _snapshot_id(evidence_hash: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"visionq/analytics/snapshot/v1/{evidence_hash}"))


def _persist_snapshot(
    connection: Connection,
    payload: dict[str, Any],
    evidence_hash: str,
) -> dict[str, Any]:
    snapshot_id = _snapshot_id(evidence_hash)
    captured_at = datetime.now(UTC)
    scope = payload["scope"]
    run_status = payload["coverage"]["run_status"]
    try:
        connection.execute(
            text("""
                INSERT INTO analytics_snapshots (
                    id, dataset_version_id, batch_id, inference_run_id,
                    metric_catalog_version, run_status, evidence_status,
                    payload_sha256, payload, pinned_corpus_version_id,
                    pinned_retrieval_index_id, captured_at
                )
                VALUES (
                    CAST(:id AS uuid),
                    CAST(:dataset_version_id AS uuid),
                    CAST(:batch_id AS uuid),
                    CAST(:inference_run_id AS uuid),
                    :metric_catalog_version,
                    :run_status,
                    :evidence_status,
                    :payload_sha256,
                    CAST(:payload AS jsonb),
                    CAST(:pinned_corpus_version_id AS uuid),
                    CAST(:pinned_retrieval_index_id AS uuid),
                    :captured_at
                )
                ON CONFLICT (id) DO NOTHING
            """),
            {
                "id": snapshot_id,
                "dataset_version_id": scope["dataset_version_id"],
                "batch_id": scope["batch_id"],
                "inference_run_id": scope["inference_run_id"],
                "metric_catalog_version": METRIC_CATALOG_VERSION,
                "run_status": run_status,
                "evidence_status": payload["coverage"]["evidence_status"],
                "payload_sha256": evidence_hash,
                "payload": json.dumps(payload, allow_nan=False),
                "pinned_corpus_version_id": None,
                "pinned_retrieval_index_id": None,
                "captured_at": captured_at,
            },
        )
        saved = (
            connection.execute(
                text("""
                    SELECT id, dataset_version_id, batch_id, inference_run_id,
                           metric_catalog_version, run_status, evidence_status,
                           payload_sha256, payload, pinned_corpus_version_id,
                           pinned_retrieval_index_id, captured_at
                    FROM analytics_snapshots
                    WHERE id = CAST(:id AS uuid)
                """),
                {"id": snapshot_id},
            )
            .mappings()
            .one()
        )
    except SQLAlchemyError as exc:
        raise SnapshotPersistenceError("analytics snapshot persistence failed") from exc
    result = _plain(dict(saved))
    if result["payload_sha256"] != evidence_hash:
        raise SnapshotIntegrityError("analytics snapshot identity conflict")
    return result


def capture_snapshot(
    engine,
    scope: AnalyticsScope,
    metric_names: list[str] | None = None,
    hook: SnapshotHook | None = None,
) -> dict[str, Any]:
    selected = normalize_metric_names(metric_names)
    with engine.connect() as connection:
        connection = connection.execution_options(isolation_level="REPEATABLE READ")
        with connection.begin():
            evidence = _build_evidence(connection, scope, selected, hook)
            evidence_hash = content_sha256(evidence)
            return _persist_snapshot(connection, evidence, evidence_hash)


def capture_context_snapshot(
    engine,
    scopes: list[tuple[str, AnalyticsScope]],
    metric_names: list[str] | None = None,
    pinned_corpus_version_id: str | None = None,
    pinned_retrieval_index_id: str | None = None,
) -> dict[str, Any]:
    selected = normalize_metric_names(metric_names)
    if not 1 <= len(scopes) <= MAX_CONTEXT_SCOPES:
        raise SnapshotContextError(
            f"snapshot requires 1..{MAX_CONTEXT_SCOPES} authorized scopes"
        )
    roles = [role for role, _ in scopes]
    if len(set(roles)) != len(roles) or not set(roles) <= CONTEXT_ROLES:
        raise SnapshotContextError(
            "scope roles must be unique primary, left or right values"
        )
    if ("left" in roles) != ("right" in roles):
        raise SnapshotContextError(
            "comparison snapshots require both left and right scopes"
        )

    with engine.connect() as connection:
        connection = connection.execution_options(isolation_level="REPEATABLE READ")
        with connection.begin():
            scope_set = []
            for role, scope in scopes:
                evidence = _build_evidence(connection, scope, selected)
                evidence["quality"] = _quality_evidence(connection, scope)
                scope_set.append({"role": role, "evidence": evidence})
            pin = _retrieval_pin(
                connection,
                pinned_corpus_version_id,
                pinned_retrieval_index_id,
            )
            payload = {
                "format": CONTEXT_FORMAT,
                "query_version": QUERY_VERSION,
                "metric_catalog_version": METRIC_CATALOG_VERSION,
                "scope_set": scope_set,
                "pinned_retrieval": pin,
            }
            if len(canonical_bytes(payload)) > MAX_CONTEXT_PAYLOAD_BYTES:
                raise SnapshotContextError(
                    "authorized snapshot evidence exceeds output size bound"
                )
            evidence_hash = content_sha256(payload)
            primary = next(
                (item for item in scope_set if item["role"] == "primary"),
                scope_set[0],
            )
            primary_scope = primary["evidence"]["scope"]
            captured_at = datetime.now(UTC)
            snapshot_id = _snapshot_id(evidence_hash)
            connection.execute(
                text("""
                    INSERT INTO analytics_snapshots (
                        id, dataset_version_id, batch_id, inference_run_id,
                        metric_catalog_version, run_status, evidence_status,
                        payload_sha256, payload, pinned_corpus_version_id,
                        pinned_retrieval_index_id, captured_at
                    )
                    VALUES (
                        CAST(:id AS uuid),
                        CAST(:dataset_version_id AS uuid),
                        CAST(:batch_id AS uuid),
                        CAST(:inference_run_id AS uuid),
                        :metric_catalog_version,
                        :run_status,
                        :evidence_status,
                        :payload_sha256,
                        CAST(:payload AS jsonb),
                        CAST(:pinned_corpus_version_id AS uuid),
                        CAST(:pinned_retrieval_index_id AS uuid),
                        :captured_at
                    )
                    ON CONFLICT (id) DO NOTHING
                """),
                {
                    "id": snapshot_id,
                    **primary_scope,
                    "metric_catalog_version": METRIC_CATALOG_VERSION,
                    "run_status": primary["evidence"]["coverage"]["run_status"],
                    "evidence_status": primary["evidence"]["coverage"][
                        "evidence_status"
                    ],
                    "payload_sha256": evidence_hash,
                    "payload": json.dumps(payload, allow_nan=False),
                    "pinned_corpus_version_id": pinned_corpus_version_id,
                    "pinned_retrieval_index_id": pinned_retrieval_index_id,
                    "captured_at": captured_at,
                },
            )
            return _snapshot_payload(connection, snapshot_id)


def _snapshot_payload(connection, snapshot_id: str) -> dict[str, Any]:
    row = (
        connection.execute(
            text("""
                SELECT id, dataset_version_id, batch_id, inference_run_id,
                       metric_catalog_version, run_status, evidence_status,
                       payload_sha256, payload, pinned_corpus_version_id,
                       pinned_retrieval_index_id, captured_at
                FROM analytics_snapshots
                WHERE id = CAST(:id AS uuid)
            """),
            {"id": snapshot_id},
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise AnalyticsScopeError("unknown analytics snapshot")
    result = _plain(dict(row))
    actual_hash = content_sha256(result["payload"])
    if actual_hash != result["payload_sha256"]:
        raise SnapshotIntegrityError("analytics snapshot checksum mismatch")
    return result


def read_snapshot(
    engine,
    snapshot_id: str,
    *,
    read_only: bool = False,
    statement_timeout_ms: int | None = None,
) -> dict[str, Any]:
    try:
        UUID(str(snapshot_id))
    except (AttributeError, TypeError, ValueError):
        raise AnalyticsScopeError("invalid analytics snapshot ID") from None
    with engine.connect() as connection:
        with connection.begin():
            if read_only:
                connection.execute(text("SET TRANSACTION READ ONLY"))
            if statement_timeout_ms is not None:
                if not 1 <= statement_timeout_ms <= 120_000:
                    raise ValueError(
                        "statement_timeout_ms is outside the supported range"
                    )
                connection.execute(
                    text("SELECT set_config('statement_timeout', :timeout, true)"),
                    {"timeout": str(statement_timeout_ms)},
                )
            return _snapshot_payload(connection, snapshot_id)


def _metric_map(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["metric_name"]: item for item in payload["metrics"]}


def compare_payloads(
    left: dict[str, Any],
    right: dict[str, Any],
    metric_names: list[str] | None = None,
) -> dict[str, Any]:
    selected = normalize_metric_names(metric_names)
    if CONTEXT_FORMAT in (left.get("format"), right.get("format")):
        raise AnalyticsCompatibilityError(
            "compare the left and right scopes within the context snapshot"
        )
    compatibility_fields = (
        ("dataset", "evidence_kind"),
        ("dataset", "release_manifest_sha256"),
        ("model", "evidence_kind"),
        ("model", "architecture"),
        ("model", "class_map_version"),
        ("model", "checkpoint_sha256"),
        ("model", "inference_config_sha256"),
        ("model", "inference_config"),
    )
    if left["scope"]["dataset_version_id"] != right["scope"]["dataset_version_id"]:
        raise AnalyticsCompatibilityError(
            "incompatible comparison: dataset version differs"
        )
    for group, field in compatibility_fields:
        if left["provenance"][group][field] != right["provenance"][group][field]:
            raise AnalyticsCompatibilityError(
                f"incompatible comparison: {group}.{field} differs"
            )
    if left["scope"]["class_id"] != right["scope"]["class_id"]:
        raise AnalyticsCompatibilityError(
            "incompatible comparison: class filters differ"
        )
    if (
        left["metric_catalog_version"] != right["metric_catalog_version"]
        or left["query_version"] != right["query_version"]
    ):
        raise AnalyticsCompatibilityError(
            "incompatible comparison: metric or query version differs"
        )

    left_metrics = _metric_map(left)
    right_metrics = _metric_map(right)
    rows = []
    for name in selected:
        if name not in left_metrics or name not in right_metrics:
            raise AnalyticsCompatibilityError(
                f"metric is absent from one snapshot: {name}"
            )
        left_metric = left_metrics[name]
        right_metric = right_metrics[name]
        if left_metric["definition_sha256"] != right_metric["definition_sha256"]:
            raise AnalyticsCompatibilityError(
                f"incompatible comparison: definition differs for {name}"
            )
        left_value = left_metric["value"]
        right_value = right_metric["value"]
        if left_value is None or right_value is None:
            absolute = None
            relative = None
            relative_reason = "one or both values are unavailable"
        else:
            absolute = right_value - left_value
            if left_value == 0:
                relative = None
                relative_reason = "zero_left_value"
            else:
                relative = absolute / left_value
                relative_reason = None
        percentage_points = (
            100 * absolute
            if absolute is not None and METRIC_CATALOG[name].unit == "fraction"
            else None
        )
        rows.append(
            {
                "metric_name": name,
                "unit": left_metric["unit"],
                "definition_sha256": left_metric["definition_sha256"],
                "left": {
                    "scope": left["scope"],
                    "value": left_value,
                    "evidence_status": left_metric["evidence_status"],
                    "denominator_name": left_metric["denominator_name"],
                    "denominator_value": left_metric["denominator_value"],
                },
                "right": {
                    "scope": right["scope"],
                    "value": right_value,
                    "evidence_status": right_metric["evidence_status"],
                    "denominator_name": right_metric["denominator_name"],
                    "denominator_value": right_metric["denominator_value"],
                },
                "absolute_delta": absolute,
                "relative_delta": relative,
                "relative_delta_reason": relative_reason,
                "percentage_point_delta": percentage_points,
            }
        )
    return {
        "format": "visionq-analytics-comparison-v1",
        "query_version": QUERY_VERSION,
        "metric_catalog_version": METRIC_CATALOG_VERSION,
        "metrics": rows,
    }


def compare_scopes(
    engine,
    left_scope: AnalyticsScope,
    right_scope: AnalyticsScope,
    metric_names: list[str] | None = None,
) -> dict[str, Any]:
    selected = normalize_metric_names(metric_names)
    with engine.connect() as connection:
        connection = connection.execution_options(isolation_level="REPEATABLE READ")
        with connection.begin():
            left = _build_evidence(connection, left_scope, selected)
            right = _build_evidence(connection, right_scope, selected)
            return compare_payloads(left, right, list(selected))


def compare_snapshots(
    engine,
    left_snapshot_id: str,
    right_snapshot_id: str,
    metric_names: list[str] | None = None,
) -> dict[str, Any]:
    for snapshot_id in (left_snapshot_id, right_snapshot_id):
        try:
            UUID(str(snapshot_id))
        except (AttributeError, TypeError, ValueError):
            raise AnalyticsScopeError("invalid analytics snapshot ID") from None
    with engine.connect() as connection:
        with connection.begin():
            left = _snapshot_payload(connection, left_snapshot_id)
            right = _snapshot_payload(connection, right_snapshot_id)
            return compare_payloads(
                left["payload"],
                right["payload"],
                metric_names,
            )
