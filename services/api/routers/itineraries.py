from fastapi import APIRouter, Query
from typing import Optional

from services.api.schemas import (
    CurrencyType, NormalizeType, SortByType,
    ItinerarySearchResponse, BestMonthResponse,
)

router = APIRouter()


@router.get("/search", response_model=ItinerarySearchResponse)
def search_itineraries(
    origin: str,
    destination: str,
    depart_date: str,
    return_date: Optional[str] = None,
    sort_by: SortByType = Query(default="balanced"),
    price_weight: float = Query(default=0.6, ge=0, le=1),
    currency: CurrencyType = Query(default="KRW"),
    normalize_by: NormalizeType = Query(default="none"),
    limit: int = Query(default=20, ge=0, le=100),
    offset: int = Query(default=0, ge=0),
):
    """GET /v1/itineraries/search — API_SPEC.md 2번 그룹"""
    raise NotImplementedError


@router.get("/best-in-month", response_model=BestMonthResponse)
def best_in_month(
    origin: str,
    destination: str,
    year_month: str,
    trip_length_days: Optional[int] = None,
    sort_by: SortByType = Query(default="balanced"),
    price_weight: float = Query(default=0.6, ge=0, le=1),
    currency: CurrencyType = Query(default="KRW"),
    normalize_by: NormalizeType = Query(default="none"),
    limit: int = Query(default=20, ge=0, le=100),
    offset: int = Query(default=0, ge=0),
):
    """GET /v1/itineraries/best-in-month — API_SPEC.md 4번 그룹"""
    raise NotImplementedError