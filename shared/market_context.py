"""
하루에 한 번, 그 날짜의 KRW-USD 환율과 WTI 유가(+ 최근 30일 평균)를 받아와
market_context 테이블에 저장한다.

- 환율: open.er-api.com (API 키 불필요, 일 단위 갱신)
- 유가: EIA(미국 에너지정보청) 공식 API (무료 키 필요 — https://www.eia.gov/opendata/register.php)
        환경변수 EIA_API_KEY 로 전달한다.

scheduler.py의 하루 1회 resync 타이밍에서 sync_daily_market_context()를 호출해서 쓴다.
"""

import os
import urllib.request
import json
from datetime import datetime, timezone, timedelta

from shared import db

KST = timezone(timedelta(hours=9))

EIA_API_KEY = os.environ.get("EIA_API_KEY", "")
# WTI(Cushing, OK) 현물가 일별 시계열 시리즈 ID
EIA_WTI_SERIES_URL = (
    "https://api.eia.gov/v2/petroleum/pri/spt/data/"
    "?frequency=daily&data[0]=value&facets[series][]=RWTC"
    "&sort[0][column]=period&sort[0][direction]=desc&length=1"
)
EXCHANGE_RATE_URL = "https://open.er-api.com/v6/latest/USD"


def _fetch_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_krw_usd_rate() -> float | None:
    """1 USD 당 몇 KRW인지 반환한다."""
    try:
        data = _fetch_json(EXCHANGE_RATE_URL)
        return float(data["rates"]["KRW"])
    except Exception as e:
        print(f"[market_context] 환율 조회 실패: {e}")
        return None


def fetch_wti_price_usd() -> float | None:
    """WTI 현물가(USD/배럴)를 반환한다. EIA_API_KEY가 없으면 조회를 건너뛴다."""
    if not EIA_API_KEY:
        print("[market_context] EIA_API_KEY가 설정되지 않아 유가 조회를 건너뜁니다. "
              "https://www.eia.gov/opendata/register.php 에서 무료로 발급받을 수 있습니다.")
        return None
    try:
        url = f"{EIA_WTI_SERIES_URL}&api_key={EIA_API_KEY}"
        data = _fetch_json(url)
        return float(data["response"]["data"][0]["value"])
    except Exception as e:
        print(f"[market_context] 유가 조회 실패: {e}")
        return None


def sync_daily_market_context() -> None:
    """오늘 날짜의 market_context가 이미 있으면 아무것도 안 하고, 없으면 새로 받아온다."""
    if db.has_market_context_for_today():
        return

    today = datetime.now(KST).date().isoformat()
    krw_usd_rate = fetch_krw_usd_rate()
    oil_price_usd = fetch_wti_price_usd()

    oil_price_30d_avg = None
    if oil_price_usd is not None:
        recent = db.get_recent_oil_prices(days=29) + [oil_price_usd]
        oil_price_30d_avg = sum(recent) / len(recent)

    db.upsert_market_context(today, krw_usd_rate, oil_price_usd, oil_price_30d_avg)
    print(f"[market_context] {today} 저장 완료: "
          f"KRW/USD={krw_usd_rate}, WTI=${oil_price_usd}, 30일평균=${oil_price_30d_avg}")


if __name__ == "__main__":
    db.init_db()
    db.init_market_context_table()
    sync_daily_market_context()