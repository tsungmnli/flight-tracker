"""
API_SPEC.md에 확정된 점수 계산 로직.
"""


def price_score(price: float, min_price: float, max_price: float) -> float:
    """검색 결과 내 최저가=100, 최고가=0이 되도록 상대 환산."""
    if max_price == min_price:
        return 100.0
    return (max_price - price) / (max_price - min_price) * 100


def _time_window_score(value_hours: float, window_start: float, window_end: float) -> float:
    """value_hours가 [window_start, window_end] 안이면 100, 벗어난 만큼 12시간을 기준으로 감점."""
    if window_start <= value_hours <= window_end:
        return 100.0
    dist = min(
        abs(value_hours - window_start), abs(value_hours - window_end),
        abs(value_hours - window_start - 24), abs(value_hours - window_end - 24),
        abs(value_hours - window_start + 24), abs(value_hours - window_end + 24),
    )
    return max(0.0, 100 - dist * (100 / 12))


def schedule_score(depart_time: str, arrive_time: str, stops: int,
                    duration_minutes: int, min_duration_minutes: int) -> float:
    """출발시간/도착시간/경유/소요시간 4개 요소를 각 25% 비중으로 평균."""
    def _to_hours(t: str) -> float:
        h, m = map(int, t.split(":"))
        return h + m / 60

    depart_score = _time_window_score(_to_hours(depart_time), 6, 11)
    arrive_score = _time_window_score(_to_hours(arrive_time), 15, 21)

    if stops == 0:
        stops_score = 100.0
    elif stops == 1:
        stops_score = 70.0
    else:
        stops_score = 40.0

    if not duration_minutes or not min_duration_minutes:
        duration_score = 100.0
    else:
        duration_score = max(0.0, min(100.0, (min_duration_minutes / duration_minutes) * 100))

    return (depart_score + arrive_score + stops_score + duration_score) / 4


def balanced_score(price_score_value: float, schedule_score_value: float,
                    price_weight: float = 0.6) -> float:
    """balanced 종합점수 = price_score * price_weight + schedule_score * (1 - price_weight)"""
    return price_score_value * price_weight + schedule_score_value * (1 - price_weight)


def normalize_price_by_oil(price: float, oil_price_then: float, oil_price_today: float) -> float | None:
    """price_normalized_oil = 그때_가격 * (오늘_유가 / 그때_유가)"""
    if not oil_price_then:
        return None
    return price * (oil_price_today / oil_price_then)


def normalize_price_by_usd_krw(price_krw: float, krw_usd_rate_today: float) -> float | None:
    """price_normalized_usd_krw = 그때_가격(KRW) / 오늘_환율"""
    if not krw_usd_rate_today:
        return None
    return price_krw / krw_usd_rate_today