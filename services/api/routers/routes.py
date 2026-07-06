from fastapi import APIRouter, Query
from typing import Optional

from services.api.schemas import AvailableRoutesResponse

router = APIRouter()


@router.get("/available", response_model=AvailableRoutesResponse)
def get_available_routes(origin: Optional[str] = Query(default=None)):
    """GET /v1/routes/available — API_SPEC.md 1번 그룹"""
    raise NotImplementedError