from fastapi import APIRouter, Query
from typing import Optional

from services.api.schemas import AvailableRoutesResponse
from shared.db import get_available_routes

router = APIRouter()


@router.get("/available", response_model=AvailableRoutesResponse)
def get_available_routes_endpoint(origin: Optional[str] = Query(default=None)):
    """GET /v1/routes/available — API_SPEC.md 1번 그룹"""
    rows = get_available_routes(origin=origin)
    return AvailableRoutesResponse(routes=rows)