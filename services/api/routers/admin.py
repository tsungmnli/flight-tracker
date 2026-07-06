import os
import secrets
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Depends

from services.api.schemas import RouteCreateRequest, AdminRoutesResponse, SystemStatus

router = APIRouter()


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
    raise NotImplementedError


@router.post("/routes", dependencies=[Depends(_require_api_key)])
def add_route(body: RouteCreateRequest):
    """POST /v1/admin/routes — body: {origin, destination, mode, horizon_days}"""
    raise NotImplementedError


@router.delete("/routes/{origin}/{destination}", dependencies=[Depends(_require_api_key)])
def deactivate_route(origin: str, destination: str):
    """DELETE /v1/admin/routes/{origin}/{destination}"""
    raise NotImplementedError


@router.get("/system/status", response_model=SystemStatus, dependencies=[Depends(_require_api_key)])
def get_system_status():
    """GET /v1/admin/system/status"""
    raise NotImplementedError