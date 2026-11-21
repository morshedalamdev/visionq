"""API-owned analytics snapshot routes."""

from __future__ import annotations

import hmac
import os

from fastapi import APIRouter, Depends, HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.engine import Engine

from analytics.metrics import AnalyticsScope, metric_catalogue
from analytics.service import (
    AnalyticsCompatibilityError,
    AnalyticsScopeError,
    SnapshotIntegrityError,
    SnapshotPersistenceError,
    capture_snapshot,
    compare_scopes,
    compare_snapshots,
    read_snapshot,
)
from api.schemas import (
    AnalyticsScopeRequest,
    ScopeComparisonRequest,
    SnapshotComparisonRequest,
    SnapshotCreateRequest,
)

router = APIRouter(prefix="/analytics", tags=["analytics"])
bearer = HTTPBearer(auto_error=False)


def require_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Security(bearer),
) -> None:
    expected = request.app.state.analytics_api_token or os.environ.get(
        "VISIONQ_ANALYTICS_API_TOKEN"
    )
    if expected is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="analytics API authorization is not configured",
        )
    supplied = credentials.credentials if credentials else ""
    if not expected or not hmac.compare_digest(supplied, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid analytics API credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


def engine_for(request: Request) -> Engine:
    return request.app.state.engine


def as_scope(request: AnalyticsScopeRequest) -> AnalyticsScope:
    return AnalyticsScope.from_values(
        str(request.dataset_version_id),
        str(request.batch_id),
        str(request.inference_run_id),
        request.class_id,
    )


def analytics_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, AnalyticsCompatibilityError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, AnalyticsScopeError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, SnapshotPersistenceError):
        return HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, SnapshotIntegrityError):
        return HTTPException(status_code=500, detail=str(exc))
    raise exc


@router.get("/metrics", dependencies=[Depends(require_token)])
def metrics() -> dict:
    return metric_catalogue()


@router.post(
    "/snapshots",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_token)],
)
def create_snapshot(
    body: SnapshotCreateRequest,
    engine: Engine = Depends(engine_for),
) -> dict:
    try:
        return capture_snapshot(engine, as_scope(body), body.metric_names)
    except (
        AnalyticsScopeError,
        SnapshotPersistenceError,
        SnapshotIntegrityError,
    ) as exc:
        raise analytics_http_error(exc) from exc


@router.get("/snapshots/{snapshot_id}", dependencies=[Depends(require_token)])
def get_snapshot(
    snapshot_id: str,
    engine: Engine = Depends(engine_for),
) -> dict:
    try:
        return read_snapshot(engine, snapshot_id)
    except (AnalyticsScopeError, SnapshotIntegrityError) as exc:
        raise analytics_http_error(exc) from exc


@router.post("/comparisons/scopes", dependencies=[Depends(require_token)])
def compare_analytics_scopes(
    body: ScopeComparisonRequest,
    engine: Engine = Depends(engine_for),
) -> dict:
    try:
        return compare_scopes(
            engine,
            as_scope(body.left),
            as_scope(body.right),
            body.metric_names,
        )
    except (
        AnalyticsCompatibilityError,
        AnalyticsScopeError,
        SnapshotPersistenceError,
    ) as exc:
        raise analytics_http_error(exc) from exc


@router.post("/comparisons/snapshots", dependencies=[Depends(require_token)])
def compare_analytics_snapshots(
    body: SnapshotComparisonRequest,
    engine: Engine = Depends(engine_for),
) -> dict:
    try:
        return compare_snapshots(
            engine,
            str(body.left_snapshot_id),
            str(body.right_snapshot_id),
            body.metric_names,
        )
    except (
        AnalyticsCompatibilityError,
        AnalyticsScopeError,
        SnapshotIntegrityError,
    ) as exc:
        raise analytics_http_error(exc) from exc
