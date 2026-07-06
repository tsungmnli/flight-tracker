from fastapi import APIRouter, Query

from services.api.schemas import CurrencyType, NormalizeType, FlightTrendResponse

router = APIRouter()


@router.get("/trend", response_model=FlightTrendResponse)
def get_flight_trend(
    origin: str,
    destination: str,
    depart_date: str,
    currency: CurrencyType = Query(default="KRW"),
    normalize_by: NormalizeType = Query(default="none"),
):
    """GET /v1/flights/trend — API_SPEC.md 3번 그룹"""
    raise NotImplementedError