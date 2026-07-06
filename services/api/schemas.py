"""
API_SPEC.md의 응답 예시를 그대로 Pydantic 모델로 옮긴 뼈대.
실제 필드 타입/검증 규칙은 구현하면서 다듬을 것.
"""

from typing import Optional, Literal
from pydantic import BaseModel, Field, ConfigDict


# ── 공통 ──────────────────────────────────────────────

CurrencyType = Literal["KRW", "USD"]
NormalizeType = Literal["none", "oil_price", "usd_krw"]
SortByType = Literal["cheapest", "best_schedule", "balanced"]


class ErrorResponse(BaseModel):
    code: str
    message: str


# ── 1. Available Routes ──────────────────────────────

class AvailableRoute(BaseModel):
    origin: str
    destination: str
    active: bool
    first_price_collected_at: Optional[str] = None
    last_price_collected_at: Optional[str] = None


class AvailableRoutesResponse(BaseModel):
    routes: list[AvailableRoute]


# ── 2/4. Itinerary Search / Best Month ───────────────

class FlightLeg(BaseModel):
    airline_name: Optional[str] = None
    depart_time: Optional[str] = None
    arrive_time: Optional[str] = None
    stops: Optional[int] = None
    price: Optional[float] = None
    price_normalized: Optional[float] = None


class ScoreBreakdown(BaseModel):
    price_score: float
    schedule_score: float


class Itinerary(BaseModel):
    rank: int
    score: float
    score_breakdown: Optional[ScoreBreakdown] = None
    outbound: FlightLeg
    inbound: Optional[FlightLeg] = None
    total_price: float
    total_price_normalized: Optional[float] = None


class ItinerarySearchResponse(BaseModel):
    depart_date: str
    return_date: Optional[str] = None
    sort_by: SortByType
    total_results: int
    itineraries: list[Itinerary]
    experimental: Optional[bool] = None


class BestMonthItinerary(BaseModel):
    rank: int
    score: float
    depart_date: str
    return_date: str
    total_price: float
    total_price_normalized: Optional[float] = None


class BestMonthResponse(BaseModel):
    year_month: str
    sort_by: SortByType
    best_itineraries: list[BestMonthItinerary]
    experimental: Optional[bool] = None


# ── 3. Flight Trend ───────────────────────────────────

class TrendPoint(BaseModel):
    collected_at: str
    days_before_departure: int
    price: float
    price_normalized: Optional[float] = None
    oil_price_usd: Optional[float] = None
    krw_usd_rate: Optional[float] = None


class DataGap(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    from_: str = Field(alias="from")
    to: str
    reason: str


class CheapestPoint(BaseModel):
    collected_at: str
    days_before_departure: int
    price: float


class AllTimeLow(BaseModel):
    price: float
    collected_at: str
    note: Optional[str] = None


class FlightTrendResponse(BaseModel):
    origin: str
    destination: str
    depart_date: str
    trend: list[TrendPoint]
    data_gaps: list[DataGap]
    cheapest_point: Optional[CheapestPoint] = None
    all_time_low: Optional[AllTimeLow] = None
    experimental: Optional[bool] = None


# ── 5. Market Context ─────────────────────────────────

class MarketContextPoint(BaseModel):
    context_date: str
    krw_usd_rate: Optional[float] = None
    oil_price_usd: Optional[float] = None
    oil_price_30d_avg: Optional[float] = None


class MarketContextResponse(BaseModel):
    context: list[MarketContextPoint]


# ── 6. Admin ───────────────────────────────────────────

class RouteCreateRequest(BaseModel):
    origin: str
    destination: str
    mode: Literal["pair", "one-way"] = "pair"
    horizon_days: int = 365


class AdminRoute(BaseModel):
    origin: str
    destination: str
    active: bool
    first_price_collected_at: Optional[str] = None
    last_price_collected_at: Optional[str] = None


class AdminRoutesResponse(BaseModel):
    routes: list[AdminRoute]


class SystemStatus(BaseModel):
    active_tracked_dates: int
    stale_tracked_dates: int
    stale_ratio: float
    last_collection_success_at: Optional[str] = None
    last_collection_error: Optional[str] = None