import calendar
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Query, HTTPException

from services.api.schemas import (
    CurrencyType, NormalizeType, SortByType,
    ItinerarySearchResponse, BestMonthResponse,
    Itinerary, ScoreBreakdown, FlightLeg, BestMonthItinerary,
)
from services.api import scoring
from shared.db import get_latest_offers, get_market_context, get_latest_krw_usd_rate

router = APIRouter()


def _duration_minutes(o: dict) -> int:
    return o.get("duration_minutes") or 0


def _normalize_leg_price(o: Optional[dict], normalize_by: str, today_oil: Optional[float],
                          today_krw_usd: Optional[float]) -> Optional[float]:
    """편도 leg 하나의 price_normalized.

    각 leg는 서로 다른 시점(collected_at)에 수집됐을 수 있으므로,
    leg 자신의 수집 시점 기준 유가/환율을 사용해 정규화한다.
    (total_price_normalized는 이 값들을 합산해서 만든다 — API_SPEC.md 응답 예시와
    outbound.price_normalized + inbound.price_normalized == total_price_normalized 관계가 성립해야 함)
    """
    if not o:
        return None
    raw_price = o.get("price_krw")
    if raw_price is None:
        return None

    if normalize_by == "usd_krw":
        if today_krw_usd:
            return scoring.normalize_price_by_usd_krw(raw_price, today_krw_usd)
        return None

    if normalize_by == "oil_price":
        collected_at = o.get("collected_at")
        if today_oil and collected_at:
            row_context = get_market_context(collected_at[:10])
            if row_context and row_context.get("oil_price_usd"):
                return scoring.normalize_price_by_oil(raw_price, row_context["oil_price_usd"], today_oil)
        return None

    return None


def _combo_price_normalized(o: Optional[dict], i: Optional[dict], normalize_by: str,
                             today_oil: Optional[float], today_krw_usd: Optional[float]) -> Optional[float]:
    """왕복(or 편도) 조합 전체의 정규화 가격 = leg별 정규화 가격의 합."""
    if normalize_by == "none":
        return None

    out_norm = _normalize_leg_price(o, normalize_by, today_oil, today_krw_usd)
    if not i:
        return out_norm

    in_norm = _normalize_leg_price(i, normalize_by, today_oil, today_krw_usd)
    if out_norm is None or in_norm is None:
        # 한쪽이라도 계산 불가능하면(해당 날짜 시장 데이터 없음 등) 합산값도 신뢰할 수 없으므로 None
        return None
    return out_norm + in_norm


def _to_leg(o: Optional[dict], currency: str, today_krw_usd: Optional[float],
            normalize_by: str, today_oil: Optional[float]) -> Optional[FlightLeg]:
    if not o:
        return None

    raw_price = o.get("price_krw")
    display_price = raw_price
    if currency == "USD" and today_krw_usd and raw_price is not None:
        display_price = raw_price / today_krw_usd

    return FlightLeg(
        airline_name=o.get("airline_name"),
        depart_time=o.get("depart_time"),
        arrive_time=o.get("arrive_time"),
        stops=o.get("stops"),
        price=display_price,
        price_normalized=_normalize_leg_price(o, normalize_by, today_oil, today_krw_usd),
    )


def _build_combos(outbound_offers: list[dict], inbound_offers: list[dict],
                   sort_by: str, price_weight: float) -> list[dict]:
    """편도 오퍼들로 조합을 만들고 점수를 매겨, sort_by 기준으로 정렬해 반환한다."""
    if not outbound_offers:
        return []

    if inbound_offers:
        combos = [(o, i) for o in outbound_offers for i in inbound_offers]
    else:
        combos = [(o, None) for o in outbound_offers]

    prices = [(o["price_krw"] or 0) + (i["price_krw"] or 0 if i else 0) for o, i in combos]
    min_price, max_price = min(prices), max(prices)
    durations = [_duration_minutes(o) + (_duration_minutes(i) if i else 0) for o, i in combos]
    min_duration = min(durations) if durations else 0

    results = []
    for (o, i), total_price in zip(combos, prices):
        p_score = scoring.price_score(total_price, min_price, max_price)

        out_sched = scoring.schedule_score(
            o.get("depart_time") or "12:00", o.get("arrive_time") or "12:00",
            o.get("stops") or 0, _duration_minutes(o), min_duration,
        )
        if i:
            in_sched = scoring.schedule_score(
                i.get("depart_time") or "12:00", i.get("arrive_time") or "12:00",
                i.get("stops") or 0, _duration_minutes(i), min_duration,
            )
            s_score = (out_sched + in_sched) / 2
        else:
            s_score = out_sched

        if sort_by == "best_schedule":
            score = s_score
        elif sort_by == "cheapest":
            score = p_score
        else:
            score = scoring.balanced_score(p_score, s_score, price_weight)

        results.append({
            "score": score,
            "breakdown": ScoreBreakdown(price_score=p_score, schedule_score=s_score),
            "outbound": o,
            "inbound": i,
            "total_price": total_price,
        })

    if sort_by == "cheapest":
        results.sort(key=lambda r: r["total_price"])
    else:
        results.sort(key=lambda r: r["score"], reverse=True)

    return results


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
    outbound_offers = get_latest_offers(origin, destination, depart_date)
    inbound_offers = get_latest_offers(destination, origin, return_date) if return_date else []

    if not outbound_offers or (return_date and not inbound_offers):
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "ROUTE_NOT_FOUND", "message": "해당 조건의 항공권 데이터가 없습니다."}},
        )

    combos = _build_combos(outbound_offers, inbound_offers, sort_by, price_weight)

    today_context = get_market_context(datetime.now(timezone.utc).date().isoformat())
    today_oil = today_context["oil_price_usd"] if today_context else None
    today_krw_usd = today_context["krw_usd_rate"] if today_context else get_latest_krw_usd_rate()

    itineraries = []
    for rank, c in enumerate(combos[offset:offset + limit], start=offset + 1):
        o, i, total_price = c["outbound"], c["inbound"], c["total_price"]

        out_leg = _to_leg(o, currency, today_krw_usd, normalize_by, today_oil)
        in_leg = _to_leg(i, currency, today_krw_usd, normalize_by, today_oil)

        total_price_normalized = _combo_price_normalized(o, i, normalize_by, today_oil, today_krw_usd)

        display_price = total_price
        if currency == "USD" and today_krw_usd:
            display_price = total_price / today_krw_usd

        itineraries.append(Itinerary(
            rank=rank,
            score=round(c["score"], 1),
            score_breakdown=ScoreBreakdown(
                price_score=round(c["breakdown"].price_score, 1),
                schedule_score=round(c["breakdown"].schedule_score, 1),
            ),
            outbound=out_leg,
            inbound=in_leg,
            total_price=display_price,
            total_price_normalized=total_price_normalized,
        ))

    return ItinerarySearchResponse(
        depart_date=depart_date,
        return_date=return_date,
        sort_by=sort_by,
        total_results=len(combos),
        itineraries=itineraries,
        experimental=True if normalize_by != "none" else None,
    )


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
    trip_length = trip_length_days if trip_length_days is not None else 3
    year, month = map(int, year_month.split("-"))
    days_in_month = calendar.monthrange(year, month)[1]

    today_context = get_market_context(datetime.now(timezone.utc).date().isoformat())
    today_oil = today_context["oil_price_usd"] if today_context else None
    today_krw_usd = today_context["krw_usd_rate"] if today_context else get_latest_krw_usd_rate()

    best_per_day = []
    for day in range(1, days_in_month + 1):
        depart = datetime(year, month, day).date()
        ret = depart + timedelta(days=trip_length)

        outbound_offers = get_latest_offers(origin, destination, depart.isoformat())
        inbound_offers = get_latest_offers(destination, origin, ret.isoformat())
        if not outbound_offers or not inbound_offers:
            continue  # 데이터 없는 날은 건너뜀

        combos = _build_combos(outbound_offers, inbound_offers, sort_by, price_weight)
        if not combos:
            continue

        top = combos[0]
        best_per_day.append({
            "depart_date": depart.isoformat(),
            "return_date": ret.isoformat(),
            "score": top["score"],
            "total_price": top["total_price"],
            "outbound": top["outbound"],
            "inbound": top["inbound"],
        })

    if sort_by == "cheapest":
        best_per_day.sort(key=lambda d: d["total_price"])
    else:
        best_per_day.sort(key=lambda d: d["score"], reverse=True)

    best_itineraries = []
    for rank, d in enumerate(best_per_day[offset:offset + limit], start=offset + 1):
        total_price = d["total_price"]
        total_price_normalized = _combo_price_normalized(
            d["outbound"], d["inbound"], normalize_by, today_oil, today_krw_usd,
        )

        display_price = total_price
        if currency == "USD" and today_krw_usd:
            display_price = total_price / today_krw_usd

        best_itineraries.append(BestMonthItinerary(
            rank=rank,
            score=round(d["score"], 1),
            depart_date=d["depart_date"],
            return_date=d["return_date"],
            total_price=display_price,
            total_price_normalized=total_price_normalized,
        ))

    return BestMonthResponse(
        year_month=year_month,
        sort_by=sort_by,
        best_itineraries=best_itineraries,
        experimental=True if normalize_by != "none" else None,
    )