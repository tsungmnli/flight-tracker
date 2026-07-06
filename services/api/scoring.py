"""
API_SPEC.md에 확정된 점수 계산 로직.
"""


def price_score(price: float, min_price: float, max_price: float) -> float:
    """검색 결과 내 최저가=100, 최고가=0이 되도록 상대 환산."""
    raise NotImplementedError


def schedule_score(depart_time: str, arrive_time: str, stops: int,
                    duration_minutes: int, min_duration_minutes: int) -> float:
    """출발시간/도착시간/경유/소요시간 4개 요소를 각 25% 비중으로 평균."""
    raise NotImplementedError


def balanced_score(price_score_value: float, schedule_score_value: float,
                    price_weight: float = 0.6) -> float:
    """balanced 종합점수 = price_score * price_weight + schedule_score * (1 - price_weight)"""
    raise NotImplementedError


def normalize_price_by_oil(price: float, oil_price_then: float, oil_price_today: float) -> float:
    """price_normalized_oil = 그때_가격 * (오늘_유가 / 그때_유가)"""
    raise NotImplementedError


def normalize_price_by_usd_krw(price_krw: float, krw_usd_rate_today: float) -> float:
    """price_normalized_usd_krw = 그때_가격(KRW) / 오늘_환율"""
    raise NotImplementedError