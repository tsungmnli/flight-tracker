import os
import secrets
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Depends

import shared.db as db
from services.api.schemas import (
    RouteCreateRequest, AdminRoutesResponse, AdminRoute, SystemStatus,
)

router = APIRouter()

STALE_HOURS = 30.0  # services/scheduler/scheduler.py의 STALE_HOURS와 동일하게 맞춘 값


def _require_api_key(x_api_key: Optional[str] = Header(default=None)):
    expected = os.environ.get("ADMIN_API_KEY")

    if not expected:
        # 서버 설정 실수(.env에 키를 안 넣은 경우)로 인증이 통째로 뚫리는 걸 막는다.
        raise HTTPException(
            status_code=500,
            detail={"error": {"code": "SERVER_MISCONFIGURED", "message": "ADMIN_API_KEY not set"}},
        )

    if x_api_key is None or not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "UNAUTHORIZED", "message": "Invalid or missing X-API-Key"}},
        )


@router.get("/routes", response_model=AdminRoutesResponse, dependencies=[Depends(_require_api_key)])
def list_all_routes():
    """GET /v1/admin/routes — 활성+중단 노선 전체"""
    rows = db.get_available_routes(active_only=False)
    return AdminRoutesResponse(routes=rows)


@router.post("/routes", dependencies=[Depends(_require_api_key)])
def add_route(body: RouteCreateRequest):
    """POST /v1/admin/routes — body: {origin, destination, mode, horizon_days}"""
    if body.mode == "pair":
        db.add_route_pair(body.origin, body.destination)
        pairs = [(body.origin, body.destination), (body.destination, body.origin)]
    else:
        db.add_route(body.origin, body.destination)
        pairs = [(body.origin, body.destination)]

    for o, d in pairs:
        db.sync_tracked_dates(o, d, horizon_days=body.horizon_days)

    added = [AdminRoute(origin=o, destination=d, active=True) for o, d in pairs]
    return AdminRoutesResponse(routes=added)


@router.delete("/routes/{origin}/{destination}", dependencies=[Depends(_require_api_key)])
def deactivate_route(origin: str, destination: str):
    """DELETE /v1/admin/routes/{origin}/{destination}"""
    db.deactivate_route(origin, destination)
    return {"origin": origin, "destination": destination, "active": False}


@router.get("/system/status", response_model=SystemStatus, dependencies=[Depends(_require_api_key)])
def get_system_status():
    """GET /v1/admin/system/status"""
    active = db.count_active_tracked_dates()
    stale = db.count_stale_tracked_dates(stale_hours=STALE_HOURS)
    ratio = (stale / active) if active > 0 else 0.0

    return SystemStatus(
        active_tracked_dates=active,
        stale_tracked_dates=stale,
        stale_ratio=round(ratio, 3),
        last_collection_success_at=db.get_last_collection_success_at(),
        last_collection_error=None,  # 스케줄러가 에러를 DB에 남기지 않아서 현재는 항상 None
    )