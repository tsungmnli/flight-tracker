from fastapi import APIRouter, Query, HTTPException
from datetime import datetime, timezone

from services.api.schemas import (
    CurrencyType, NormalizeType, FlightTrendResponse,
    TrendPoint, DataGap, CheapestPoint, AllTimeLow,
)
from services.api import scoring
from shared.db import get_leg_price_history, get_all_time_low, get_market_context, get_latest_krw_usd_rate

router = APIRouter()

GAP_THRESHOLD_HOURS = 36  # 스케줄러가 하루 1회 도는 걸 기준으로, 이보다 더 벌어지면 결측 구간으로 본다


@router.get("/trend", response_model=FlightTrendResponse)
def get_flight_trend(
    origin: str,
    destination: str,
    depart_date: str,
    currency: CurrencyType = Query(default="KRW"),
    normalize_by: NormalizeType = Query(default="none"),
):
    """GET /v1/flights/trend — API_SPEC.md 3번 그룹"""
    rows = get_leg_price_history(origin, destination, depart_date)
    if not rows:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "ROUTE_NOT_FOUND", "message": "해당 노선/출발일의 가격 데이터가 없습니다."}},
        )

    today_context = get_market_context(datetime.now(timezone.utc).date().isoformat())
    today_oil = today_context["oil_price_usd"] if today_context else None
    today_krw_usd = today_context["krw_usd_rate"] if today_context else get_latest_krw_usd_rate()

    trend = []
    for r in rows:
        price = r["min_price_krw"]
        if currency == "USD" and today_krw_usd:
            price = price / today_krw_usd

        row_context = get_market_context(r["collected_at"][:10])

        price_normalized = None
        if normalize_by == "oil_price" and today_oil and row_context and row_context["oil_price_usd"]:
            price_normalized = scoring.normalize_price_by_oil(price, row_context["oil_price_usd"], today_oil)
        elif normalize_by == "usd_krw" and today_krw_usd:
            price_normalized = scoring.normalize_price_by_usd_krw(r["min_price_krw"], today_krw_usd)

        trend.append(TrendPoint(
            collected_at=r["collected_at"],
            days_before_departure=r["days_before_departure"],
            price=price,
            price_normalized=price_normalized,
            oil_price_usd=row_context["oil_price_usd"] if row_context else None,
            krw_usd_rate=row_context["krw_usd_rate"] if row_context else None,
        ))

    # 연속 수집 시각 간격이 임계치보다 크면 결측 구간으로 표시
    data_gaps = []
    for prev, curr in zip(trend, trend[1:]):
        t1 = datetime.fromisoformat(prev.collected_at.replace("Z", "+00:00"))
        t2 = datetime.fromisoformat(curr.collected_at.replace("Z", "+00:00"))
        if (t2 - t1).total_seconds() / 3600 > GAP_THRESHOLD_HOURS:
            data_gaps.append(DataGap(**{"from": prev.collected_at, "to": curr.collected_at, "reason": "collection_failed"}))

    cheapest = min(trend, key=lambda t: t.price)
    cheapest_point = CheapestPoint(
        collected_at=cheapest.collected_at,
        days_before_departure=cheapest.days_before_departure,
        price=cheapest.price,
    )

    all_time_low = None
    atl_row = get_all_time_low(origin, destination)
    if atl_row:
        atl_price = atl_row["price_krw"]
        if currency == "USD" and today_krw_usd:
            atl_price = atl_price / today_krw_usd
        all_time_low = AllTimeLow(
            price=atl_price,
            collected_at=atl_row["collected_at"],
            note=f"이 노선({origin}-{destination}) 전체 출발일 통틀어 역대 최저가",
        )

    return FlightTrendResponse(
        origin=origin,
        destination=destination,
        depart_date=depart_date,
        trend=trend,
        data_gaps=data_gaps,
        cheapest_point=cheapest_point,
        all_time_low=all_time_low,
        experimental=True if normalize_by != "none" else None,
    )