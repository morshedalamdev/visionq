"""Bounded read-only dashboard APIs and controlled upload requests."""

from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from PIL import Image, UnidentifiedImageError
from sqlalchemy import text
from sqlalchemy.engine import Engine

from api.analytics import engine_for, require_token
from api.dashboard_schemas import (
    AgentFixtureResponse,
    BatchListResponse,
    DatasetListResponse,
    DatasetSummaryResponse,
    RunDetailResponse,
    RunListResponse,
    RunResultsResponse,
    UploadListResponse,
    UploadRequestResponse,
)
from worker.catalog_store import check_blob
from worker.validation import CLASSES, sha256

router = APIRouter(prefix="/app", tags=["application"])
UPLOAD_LIMIT = 20_000_000
PIXEL_LIMIT = 10_000_000
ALLOWED_MEDIA = {"image/png", "image/jpeg"}
DEFAULT_LIMIT = 25
MAX_LIMIT = 100


def _plain(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_plain(item) for item in value]
    return value


def page_values(limit: int, offset: int) -> tuple[int, int]:
    if not 1 <= limit <= MAX_LIMIT or offset < 0:
        raise HTTPException(422, "limit must be 1..100 and offset non-negative")
    return limit, offset


def page(items: list, limit: int, offset: int):
    visible = items[:limit]
    return {
        "limit": limit,
        "offset": offset,
        "has_more": len(items) > limit,
    }, visible


@router.get(
    "/datasets",
    dependencies=[Depends(require_token)],
    response_model=DatasetListResponse,
)
def list_datasets(
    engine: Engine = Depends(engine_for),
    evidence_kind: str | None = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
):
    limit, offset = page_values(limit, offset)
    if evidence_kind not in (None, "synthetic", "released"):
        raise HTTPException(422, "invalid evidence_kind")
    with engine.connect() as connection:
        rows = (
            connection.execute(
                text("""
                    SELECT
                        CAST(dv.id AS text) AS id,
                        dv.dataset_name, dv.version, dv.evidence_kind,
                        dv.release_manifest_sha256, dv.created_at,
                        count(DISTINCT di.asset_id) AS asset_count,
                        count(DISTINCT b.id) AS batch_count,
                        max(irun.status) FILTER (
                            WHERE irun.id IS NOT NULL
                        ) AS latest_ingestion_status,
                        count(DISTINCT q.id) FILTER (
                            WHERE q.severity = 'error'
                        ) AS error_quality_issue_count,
                        count(DISTINCT q.id) FILTER (
                            WHERE q.severity = 'warning'
                        ) AS warning_quality_issue_count
                    FROM dataset_versions AS dv
                    LEFT JOIN dataset_items AS di
                      ON di.dataset_version_id = dv.id
                    LEFT JOIN batches AS b
                      ON b.dataset_version_id = dv.id
                    LEFT JOIN ingestion_runs AS irun
                      ON irun.dataset_version_id = dv.id
                    LEFT JOIN quality_issues AS q
                      ON q.dataset_version_id = dv.id
                    WHERE (CAST(:evidence_kind AS text) IS NULL
                       OR dv.evidence_kind = CAST(:evidence_kind AS text))
                    GROUP BY dv.id
                    ORDER BY dv.created_at DESC, dv.id DESC
                    LIMIT :fetch_limit OFFSET :offset
                """),
                {
                    "evidence_kind": evidence_kind,
                    "fetch_limit": limit + 1,
                    "offset": offset,
                },
            )
            .mappings()
            .all()
        )
    paging, visible = page(rows, limit, offset)
    return {"items": [_plain(dict(row)) for row in visible], "page": paging}


@router.get(
    "/datasets/{dataset_id}",
    dependencies=[Depends(require_token)],
    response_model=DatasetSummaryResponse,
)
def dataset_summary(dataset_id: UUID, engine: Engine = Depends(engine_for)):
    with engine.connect() as connection:
        dataset = (
            connection.execute(
                text("""
                    SELECT CAST(dv.id AS text) AS id, dv.dataset_name,
                           dv.version, dv.evidence_kind,
                           dv.release_manifest_sha256, dv.created_at,
                           (SELECT count(*) FROM dataset_items
                            WHERE dataset_version_id = dv.id) AS asset_count,
                           (SELECT count(*) FROM batches
                            WHERE dataset_version_id = dv.id) AS batch_count,
                           (SELECT status FROM ingestion_runs
                            WHERE dataset_version_id = dv.id) AS
                               latest_ingestion_status,
                           (SELECT count(*) FROM quality_issues
                            WHERE dataset_version_id = dv.id
                              AND severity = 'error') AS
                               error_quality_issue_count,
                           (SELECT count(*) FROM quality_issues
                            WHERE dataset_version_id = dv.id
                              AND severity = 'warning') AS
                               warning_quality_issue_count
                    FROM dataset_versions AS dv
                    WHERE dv.id = CAST(:id AS uuid)
                """),
                {"id": str(dataset_id)},
            )
            .mappings()
            .one_or_none()
        )
        if dataset is None:
            raise HTTPException(404, "unknown dataset version")
        splits = (
            connection.execute(
                text("""
                    SELECT split, count(*) AS count
                    FROM dataset_items
                    WHERE dataset_version_id = CAST(:id AS uuid)
                    GROUP BY split
                    ORDER BY split
                """),
                {"id": str(dataset_id)},
            )
            .mappings()
            .all()
        )
        quality = (
            connection.execute(
                text("""
                    SELECT rule_id, severity, count(*) AS count,
                           count(DISTINCT asset_id) FILTER (
                               WHERE asset_id IS NOT NULL
                           ) AS asset_count
                    FROM quality_issues
                    WHERE dataset_version_id = CAST(:id AS uuid)
                    GROUP BY rule_id, severity
                    ORDER BY rule_id, severity
                """),
                {"id": str(dataset_id)},
            )
            .mappings()
            .all()
        )
    return {
        "dataset": _plain(dict(dataset)),
        "splits": {row["split"]: row["count"] for row in splits},
        "quality_by_rule": [_plain(dict(row)) for row in quality],
    }


@router.get(
    "/batches",
    dependencies=[Depends(require_token)],
    response_model=BatchListResponse,
)
def list_batches(
    engine: Engine = Depends(engine_for),
    dataset_version_id: UUID | None = None,
    split: str | None = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
):
    limit, offset = page_values(limit, offset)
    if split not in (None, "train", "validation", "test"):
        raise HTTPException(422, "invalid split")
    with engine.connect() as connection:
        rows = (
            connection.execute(
                text("""
                    SELECT CAST(b.id AS text) AS id,
                           CAST(b.dataset_version_id AS text) AS dataset_version_id,
                           b.kind, b.split, b.member_count,
                           b.membership_sha256, b.created_at,
                           CAST(latest.id AS text) AS latest_run_id,
                           latest.status AS latest_run_status
                    FROM batches AS b
                    LEFT JOIN LATERAL (
                        SELECT id, status
                        FROM inference_runs
                        WHERE batch_id = b.id
                        ORDER BY created_at DESC, id DESC
                        LIMIT 1
                    ) AS latest ON true
                    WHERE (CAST(:dataset AS uuid) IS NULL
                       OR b.dataset_version_id = CAST(:dataset AS uuid))
                      AND (CAST(:split AS text) IS NULL
                           OR b.split = CAST(:split AS text))
                    ORDER BY b.created_at DESC, b.id DESC
                    LIMIT :fetch_limit OFFSET :offset
                """),
                {
                    "dataset": str(dataset_version_id) if dataset_version_id else None,
                    "split": split,
                    "fetch_limit": limit + 1,
                    "offset": offset,
                },
            )
            .mappings()
            .all()
        )
    paging, visible = page(rows, limit, offset)
    return {"items": [_plain(dict(row)) for row in visible], "page": paging}


RUN_SELECT = """
    SELECT CAST(r.id AS text) AS id,
           CAST(r.dataset_version_id AS text) AS dataset_version_id,
           CAST(r.batch_id AS text) AS batch_id,
           CAST(r.model_id AS text) AS model_id,
           r.status, m.evidence_kind, m.architecture,
           m.checkpoint_sha256 AS model_sha256, r.expected_items,
           count(ir.asset_id) FILTER (WHERE ir.status = 'succeeded')
               AS succeeded_items,
           count(ir.asset_id) FILTER (WHERE ir.status = 'failed')
               AS failed_items,
           count(ir.asset_id) FILTER (WHERE ir.status = 'pending')
               AS pending_items,
           count(ir.asset_id) FILTER (WHERE ir.status = 'running')
               AS running_items,
           r.started_at, r.finished_at, r.created_at, r.config
    FROM inference_runs AS r
    JOIN models AS m ON m.id = r.model_id
    LEFT JOIN image_results AS ir ON ir.run_id = r.id
"""


@router.get(
    "/runs",
    dependencies=[Depends(require_token)],
    response_model=RunListResponse,
)
def list_runs(
    engine: Engine = Depends(engine_for),
    dataset_version_id: UUID | None = None,
    batch_id: UUID | None = None,
    model_id: UUID | None = None,
    status: str | None = None,
    created_after: datetime | None = None,
    created_before: datetime | None = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
):
    limit, offset = page_values(limit, offset)
    if status not in (None, "pending", "running", "succeeded", "partial", "failed"):
        raise HTTPException(422, "invalid run status")
    with engine.connect() as connection:
        rows = (
            connection.execute(
                text(
                    RUN_SELECT
                    + """
                    WHERE (CAST(:dataset AS uuid) IS NULL
                           OR r.dataset_version_id =
                           CAST(:dataset AS uuid))
                      AND (CAST(:batch AS uuid) IS NULL
                           OR r.batch_id = CAST(:batch AS uuid))
                      AND (CAST(:model AS uuid) IS NULL
                           OR r.model_id = CAST(:model AS uuid))
                      AND (CAST(:status AS text) IS NULL
                           OR r.status = CAST(:status AS text))
                      AND (CAST(:created_after AS timestamptz) IS NULL
                           OR r.created_at >=
                              CAST(:created_after AS timestamptz))
                      AND (CAST(:created_before AS timestamptz) IS NULL
                           OR r.created_at <=
                              CAST(:created_before AS timestamptz))
                    GROUP BY r.id, m.id
                    ORDER BY r.created_at DESC, r.id DESC
                    LIMIT :fetch_limit OFFSET :offset
                    """
                ),
                {
                    "dataset": str(dataset_version_id) if dataset_version_id else None,
                    "batch": str(batch_id) if batch_id else None,
                    "model": str(model_id) if model_id else None,
                    "status": status,
                    "created_after": (
                        created_after.isoformat() if created_after else None
                    ),
                    "created_before": (
                        created_before.isoformat() if created_before else None
                    ),
                    "fetch_limit": limit + 1,
                    "offset": offset,
                },
            )
            .mappings()
            .all()
        )
    paging, visible = page(rows, limit, offset)
    return {"items": [_plain(dict(row)) for row in visible], "page": paging}


@router.get(
    "/runs/{run_id}",
    dependencies=[Depends(require_token)],
    response_model=RunDetailResponse,
)
def run_detail(run_id: UUID, engine: Engine = Depends(engine_for)):
    with engine.connect() as connection:
        row = (
            connection.execute(
                text(
                    RUN_SELECT
                    + """
                    JOIN batches AS b ON b.id = r.batch_id
                    JOIN dataset_versions AS dv ON dv.id = r.dataset_version_id
                    WHERE r.id = CAST(:id AS uuid)
                    GROUP BY r.id, m.id, b.id, dv.id
                    """
                ),
                {"id": str(run_id)},
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise HTTPException(404, "unknown inference run")
        detail = (
            connection.execute(
                text("""
                    SELECT b.kind AS batch_kind, b.split AS batch_split,
                           b.membership_sha256, m.classes,
                           r.config_sha256, m.inference_config_sha256
                               AS model_config_sha256,
                           m.inference_config, dv.dataset_name,
                           dv.version AS dataset_release,
                           dv.evidence_kind AS dataset_evidence_kind
                    FROM inference_runs AS r
                    JOIN batches AS b ON b.id = r.batch_id
                    JOIN models AS m ON m.id = r.model_id
                    JOIN dataset_versions AS dv
                      ON dv.id = r.dataset_version_id
                    WHERE r.id = CAST(:id AS uuid)
                """),
                {"id": str(run_id)},
            )
            .mappings()
            .one()
        )
    return _plain({**dict(row), **dict(detail)})


@router.get(
    "/runs/{run_id}/images",
    dependencies=[Depends(require_token)],
    response_model=RunResultsResponse,
)
def run_images(
    run_id: UUID,
    engine: Engine = Depends(engine_for),
    status: str | None = None,
    limit: int = 20,
    offset: int = 0,
):
    limit, offset = page_values(limit, offset)
    if status not in (None, "pending", "running", "succeeded", "failed"):
        raise HTTPException(422, "invalid image status")
    with engine.connect() as connection:
        known = connection.scalar(
            text("SELECT 1 FROM inference_runs WHERE id = CAST(:id AS uuid)"),
            {"id": str(run_id)},
        )
        if known is None:
            raise HTTPException(404, "unknown inference run")
        rows = (
            connection.execute(
                text("""
                    SELECT CAST(ir.asset_id AS text) AS asset_id, ir.status,
                           ir.image_sha256, a.width, a.height,
                           ir.detection_count, ir.raw_prediction_count,
                           ir.latency_ms, ir.attempts, ir.last_error,
                           ov.overlay_sha256
                    FROM image_results AS ir
                    JOIN assets AS a ON a.id = ir.asset_id
                    LEFT JOIN image_overlays AS ov
                      ON ov.run_id = ir.run_id AND ov.asset_id = ir.asset_id
                    WHERE ir.run_id = CAST(:run AS uuid)
                      AND (CAST(:status AS text) IS NULL
                           OR ir.status = CAST(:status AS text))
                    ORDER BY ir.asset_id
                    LIMIT :fetch_limit OFFSET :offset
                """),
                {
                    "run": str(run_id),
                    "status": status,
                    "fetch_limit": limit + 1,
                    "offset": offset,
                },
            )
            .mappings()
            .all()
        )
        visible_rows = rows[:limit]
        detections = (
            connection.execute(
                text("""
                    SELECT CAST(d.asset_id AS text) AS asset_id, d.ordinal,
                           d.class_id, d.confidence, d.box_xmin, d.box_ymin,
                           d.box_xmax, d.box_ymax
                    FROM detections AS d
                    WHERE d.run_id = CAST(:run AS uuid)
                      AND d.asset_id = ANY(CAST(:assets AS uuid[]))
                    ORDER BY d.asset_id, d.ordinal
                """),
                {
                    "run": str(run_id),
                    "assets": [row["asset_id"] for row in visible_rows],
                },
            )
            .mappings()
            .all()
        )
    by_asset: dict[str, list] = {}
    for detection in detections:
        item = dict(detection)
        item["class_name"] = CLASSES[item["class_id"]]
        by_asset.setdefault(item.pop("asset_id"), []).append(_plain(item))
    items = []
    for row in visible_rows:
        item = _plain(dict(row))
        item["image_url"] = f"/app/artifacts/{item['image_sha256']}"
        item["overlay_url"] = (
            f"/app/artifacts/{item['overlay_sha256']}"
            if item["overlay_sha256"]
            else None
        )
        item["detections"] = by_asset.get(item["asset_id"], [])
        items.append(item)
    return {
        "items": items,
        "page": {
            "limit": limit,
            "offset": offset,
            "has_more": len(rows) > limit,
        },
    }


def artifact_root(request: Request) -> Path:
    root = request.app.state.artifact_root
    if root is None:
        raise HTTPException(503, "artifact storage is not configured")
    return root


@router.get("/artifacts/{checksum}", dependencies=[Depends(require_token)])
def artifact(checksum: str, request: Request, root: Path = Depends(artifact_root)):
    if len(checksum) != 64 or any(c not in "0123456789abcdef" for c in checksum):
        raise HTTPException(422, "invalid artifact checksum")
    with request.app.state.engine.connect() as connection:
        artifact = (
            connection.execute(
                text("""
                    SELECT byte_count
                    FROM catalog_artifacts
                    WHERE sha256 = :checksum
                      AND (
                        EXISTS (SELECT 1 FROM assets WHERE raw_sha256 = :checksum)
                        OR EXISTS (
                            SELECT 1 FROM image_results
                            WHERE image_sha256 = :checksum
                        )
                        OR EXISTS (
                            SELECT 1 FROM image_overlays
                            WHERE overlay_sha256 = :checksum
                        )
                      )
                """),
                {"checksum": checksum},
            )
            .mappings()
            .one_or_none()
        )
    if artifact is None:
        raise HTTPException(404, "unknown artifact")
    path = root / "catalog/objects" / checksum
    try:
        check_blob(root, checksum, artifact["byte_count"])
    except (OSError, ValueError):
        raise HTTPException(503, "artifact is missing or corrupt") from None
    try:
        with Image.open(path) as image:
            image.load()
            converted = io.BytesIO()
            image.convert("RGB").save(converted, format="PNG")
        return Response(converted.getvalue(), media_type="image/png")
    except UnidentifiedImageError as exc:
        raise HTTPException(503, "artifact is not a supported image") from exc


def upload_path(root: Path, checksum: str) -> Path:
    if root.is_symlink():
        raise HTTPException(503, "upload storage cannot be a symlink")
    base = root / "uploads" / "objects"
    if base.is_symlink():
        raise HTTPException(503, "upload storage cannot be a symlink")
    base.mkdir(parents=True, exist_ok=True)
    destination = base / checksum
    if destination.is_symlink():
        raise HTTPException(503, "upload artifact cannot be a symlink")
    return destination


@router.post(
    "/uploads",
    dependencies=[Depends(require_token)],
    status_code=201,
    response_model=UploadRequestResponse,
)
async def upload_image(
    request: Request,
    file: UploadFile = File(...),
    dataset_version_id: str | None = Form(None),
    batch_id: str | None = Form(None),
):
    root = artifact_root(request)
    original = Path(file.filename or "").name
    if not original or len(original) > 255 or file.content_type not in ALLOWED_MEDIA:
        raise HTTPException(422, "only PNG and JPEG images are accepted")
    content = await file.read(UPLOAD_LIMIT + 1)
    if not content or len(content) > UPLOAD_LIMIT:
        raise HTTPException(413, "image must not exceed 20 MB")
    try:
        with Image.open(io.BytesIO(content)) as decoded:
            decoded.load()
            expected = {"image/png": "PNG", "image/jpeg": "JPEG"}[file.content_type]
            if decoded.format != expected:
                raise HTTPException(422, "image encoding differs from file type")
            width, height = decoded.size
            if width * height > PIXEL_LIMIT:
                raise HTTPException(422, "image exceeds the 10 megapixel limit")
    except UnidentifiedImageError as exc:
        raise HTTPException(422, "image cannot be decoded") from exc
    try:
        dataset = str(UUID(dataset_version_id)) if dataset_version_id else None
        batch = str(UUID(batch_id)) if batch_id else None
    except ValueError:
        raise HTTPException(422, "invalid upload scope UUID") from None
    if bool(batch) != bool(dataset):
        raise HTTPException(422, "batch upload scope requires a dataset version")
    with request.app.state.engine.connect() as connection:
        if dataset is not None:
            if (
                connection.scalar(
                    text("SELECT 1 FROM dataset_versions WHERE id = CAST(:id AS uuid)"),
                    {"id": dataset},
                )
                is None
            ):
                raise HTTPException(422, "unknown upload dataset version")
        if batch is not None and (
            connection.scalar(
                text("""
                    SELECT 1
                    FROM batches
                    WHERE id = CAST(:batch AS uuid)
                      AND dataset_version_id = CAST(:dataset AS uuid)
                """),
                {"batch": batch, "dataset": dataset},
            )
            is None
        ):
            raise HTTPException(422, "batch does not belong to upload dataset")
    checksum = sha256(content)
    destination = upload_path(root, checksum)
    if destination.exists():
        try:
            existing = destination.read_bytes()
        except OSError as exc:
            raise HTTPException(503, "stored upload cannot be read") from exc
        if existing != content:
            raise HTTPException(503, "upload storage checksum conflict")
    else:
        temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
        try:
            temporary.write_bytes(content)
            temporary.replace(destination)
        except OSError as exc:
            raise HTTPException(503, "upload artifact could not be persisted") from exc
        finally:
            temporary.unlink(missing_ok=True)
    request_id = str(uuid4())
    try:
        with request.app.state.engine.begin() as connection:
            inserted = (
                connection.execute(
                    text("""
                    INSERT INTO image_upload_requests (
                        id, original_filename, content_sha256, byte_count,
                        media_type, width, height, artifact_uri,
                        dataset_version_id, batch_id, status,
                        inference_state
                    ) VALUES (
                        CAST(:id AS uuid), :original_filename, :checksum,
                        :byte_count, :media_type, :width, :height,
                        :artifact_uri, CAST(:dataset AS uuid),
                        CAST(:batch AS uuid), 'ready',
                        CASE WHEN CAST(:batch AS uuid) IS NULL
                             THEN 'not_started'
                             ELSE 'pending_registration'
                        END
                    )
                    ON CONFLICT (content_sha256) DO NOTHING
                    RETURNING *
                """),
                    {
                        "id": request_id,
                        "original_filename": original,
                        "checksum": checksum,
                        "byte_count": len(content),
                        "media_type": file.content_type,
                        "width": width,
                        "height": height,
                        "artifact_uri": f"uploads/objects/{checksum}",
                        "dataset": dataset,
                        "batch": batch,
                    },
                )
                .mappings()
                .one_or_none()
            )
            if inserted is None:
                inserted = (
                    connection.execute(
                        text("""
                            SELECT *
                            FROM image_upload_requests
                            WHERE content_sha256 = :checksum
                        """),
                        {"checksum": checksum},
                    )
                    .mappings()
                    .one()
                )
                saved_dataset = (
                    str(inserted["dataset_version_id"])
                    if inserted["dataset_version_id"]
                    else None
                )
                saved_batch = (
                    str(inserted["batch_id"]) if inserted["batch_id"] else None
                )
                if saved_dataset != dataset or saved_batch != batch:
                    raise HTTPException(
                        409,
                        "identical upload already belongs to a different scope",
                    )
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(503, "upload request could not be persisted") from exc
    item = _plain(dict(inserted))
    item["artifact_url"] = f"/app/uploads/{item['id']}/image"
    return item


@router.get(
    "/uploads",
    dependencies=[Depends(require_token)],
    response_model=UploadListResponse,
)
def list_uploads(
    request: Request,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
):
    limit, offset = page_values(limit, offset)
    with request.app.state.engine.connect() as connection:
        rows = (
            connection.execute(
                text("""
                    SELECT *
                    FROM image_upload_requests
                    ORDER BY created_at DESC, id DESC
                    LIMIT :fetch_limit OFFSET :offset
                """),
                {"fetch_limit": limit + 1, "offset": offset},
            )
            .mappings()
            .all()
        )
    items = []
    for row in rows[:limit]:
        item = _plain(dict(row))
        item["artifact_url"] = f"/app/uploads/{item['id']}/image"
        items.append(item)
    return {
        "items": items,
        "page": {
            "limit": limit,
            "offset": offset,
            "has_more": len(rows) > limit,
        },
    }


@router.get(
    "/uploads/{upload_id}",
    dependencies=[Depends(require_token)],
    response_model=UploadRequestResponse,
)
def get_upload(upload_id: UUID, request: Request):
    with request.app.state.engine.connect() as connection:
        row = (
            connection.execute(
                text(
                    "SELECT * FROM image_upload_requests WHERE id = CAST(:id AS uuid)"
                ),
                {"id": str(upload_id)},
            )
            .mappings()
            .one_or_none()
        )
    if row is None:
        raise HTTPException(404, "unknown upload request")
    item = _plain(dict(row))
    item["artifact_url"] = f"/app/uploads/{item['id']}/image"
    return item


@router.get("/uploads/{upload_id}/image", dependencies=[Depends(require_token)])
def upload_image_bytes(upload_id: UUID, request: Request):
    root = artifact_root(request)
    with request.app.state.engine.connect() as connection:
        row = (
            connection.execute(
                text("""
                    SELECT content_sha256, byte_count, media_type
                    FROM image_upload_requests
                    WHERE id = CAST(:id AS uuid)
                """),
                {"id": str(upload_id)},
            )
            .mappings()
            .one_or_none()
        )
    if row is None:
        raise HTTPException(404, "unknown upload request")
    path = root / "uploads/objects" / row["content_sha256"]
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise HTTPException(503, "upload artifact is missing") from exc
    if len(data) != row["byte_count"] or sha256(data) != row["content_sha256"]:
        raise HTTPException(503, "upload artifact checksum mismatch")
    return FileResponse(path, media_type=row["media_type"])


@router.get("/agent-fixture", dependencies=[Depends(require_token)])
def agent_fixture() -> AgentFixtureResponse:
    return AgentFixtureResponse(
        id="fixture-answer-v1",
        evidence_kind="development-fixture",
        question="What can the current prediction ratio tell us?",
        status="partial",
        answer=(
            "Fixture only: the captured ratio describes images with persisted "
            "predictions among successful processed images. It is not product "
            "defect prevalence or model accuracy."
        ),
        numeric_claims=[
            {
                "reference": "metric-fixture-1",
                "metric_name": "prediction_image_ratio",
                "status": "fixture",
                "limitation": "Development contract; not a live answer.",
            }
        ],
        citations=[
            {
                "reference": "citation-fixture-1",
                "source": "docs/design/architecture.md",
                "section": "Metric catalogue",
                "status": "fixture",
            }
        ],
        verification_status="fixture-not-verified",
        tool_trace=[
            {
                "tool": "get_batch_metrics",
                "status": "fixture",
                "note": "No live MCP call was made.",
            }
        ],
    )
