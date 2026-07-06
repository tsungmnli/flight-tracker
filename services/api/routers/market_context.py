from fastapi import APIRouter, Query, HTTPException
from typing import Optional

from services.api.schemas import MarketContextResponse, MarketContextPoint
from shared.db import get_market_context, get_market_context_range

router = APIRouter()


@router.get("", response_model=MarketContextResponse)
def get_market_context_endpoint(
    date: Optional[str] = Query(default=None),
    date_from: Optional[str] = Query(default=None),
    date_to: Optional[str] = Query(default=None),
):
    """GET /v1/market-context — API_SPEC.md 5번 그룹"""
    if date and (date_from or date_to):
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "INVALID_PARAMS", "message": "date와 date_from/date_to는 함께 쓸 수 없습니다."}},
        )

    if date:
        row = get_market_context(date)
        rows = [row] if row else []
    else:
        rows = get_market_context_range(date_from, date_to)

    context = [
        MarketContextPoint(
            context_date=r["context_date"],
            krw_usd_rate=r["krw_usd_rate"],
            oil_price_usd=r["oil_price_usd"],
            oil_price_30d_avg=r["oil_price_30d_avg"],
        )
        for r in rows
    ]
    return MarketContextResponse(context=context)