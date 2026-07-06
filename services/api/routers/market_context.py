from fastapi import APIRouter, Query
from typing import Optional

from services.api.schemas import MarketContextResponse

router = APIRouter()


@router.get("", response_model=MarketContextResponse)
def get_market_context(
    date: Optional[str] = Query(default=None),
    date_from: Optional[str] = Query(default=None),
    date_to: Optional[str] = Query(default=None),
):
    """GET /v1/market-context — API_SPEC.md 5번 그룹"""
    raise NotImplementedError