"""
Google Flights 응답을 Playwright로 가로채서 response.txt / response.json으로 저장하는 스크립트.
"""

import argparse
import asyncio
import re
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from playwright.async_api import async_playwright, Response

import db

# ── 설정값 ────────────────────────────────────────────────────────────────

USER_DATA_DIR = Path("./playwright_profile")


def build_search_url(
    origin: str,
    destination: str,
    depart_date: str,
    return_date: str | None,
) -> str:
    """
    자연어 쿼리로 Google Flights 검색 URL을 만든다.
    """
    query = f"Flights from {origin} to {destination} on {depart_date}"
    if return_date:
        query += f" through {return_date}"
    else:
        query += " one way"
    url = "https://www.google.com/travel/flights?q=" + urllib.parse.quote(query) + "&hl=en-US&curr=USD"
    return url


def fetch_usd_krw_rate() -> float:
    """
    1 USD당 KRW 환율을 조회한다. price_krw를 price_usd로 환산하는 데 쓰인다.
    무료 API(키 불필요)를 쓰며, 실패 시 예외를 던진다 -> 호출부에서 실패 처리를
    결정하게 한다 (여기서는 price_usd를 그냥 None으로 두고 계속 진행).
    """
    with urllib.request.urlopen("https://open.er-api.com/v6/latest/USD", timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return float(data["rates"]["KRW"])


TARGET_URL_PATTERN = re.compile(
    r"https://www\.google\.com/_/FlightsFrontendUi/data/"
    r"travel\.frontend\.flights\.FlightsFrontendService/GetShoppingResults"
)

# OUTPUT_DIR = Path("./captured_responses")
# DATA_PATH = OUTPUT_DIR / "data.json"
# ALL_RESPONSES_LOG_PATH = OUTPUT_DIR / "all_responses.log"

# XHR/HTML 캡처가 올 때마다 번호를 하나씩 늘려가며 response_NNN.txt / response_NNN.json
# 파일 쌍을 만들기 위한 전역 카운터. (핸들러들은 await 없이 카운터를 증가시키므로
# asyncio 이벤트 루프 상에서 동시에 여러 콜백이 실행되어도 번호가 겹치지 않는다.)
# _response_counter = 0


# def _next_response_paths() -> tuple[Path, Path]:
#     """호출할 때마다 response_001.txt/json, response_002.txt/json ... 순서로
#     다음 파일 경로 쌍을 반환한다."""
#     global _response_counter
#     _response_counter += 1
#     n = _response_counter
#     txt_path = OUTPUT_DIR / f"response_{n:03d}.txt"
#     json_path = OUTPUT_DIR / f"response_{n:03d}.json"
#     return txt_path, json_path


# ── 필드 매핑 (response.json -> data.json) ─────────────────────────────────

def hm_to_str(hm):
    """[시,분] 또는 [시]만 있는 경우(분=0 생략됨) 모두 처리."""
    if hm is None:
        return None
    h = hm[0]
    m = hm[1] if len(hm) > 1 else 0
    return f"{h:02d}:{m:02d}"


def ymd_to_str(ymd):
    if ymd is None:
        return None
    y, m, d = ymd
    return f"{y:04d}-{m:02d}-{d:02d}"


def looks_like_itinerary(x) -> bool:
    """
    itinerary 엔트리 시그니처: [leg, price_block, ...] 형태의 11개 원소 리스트.
    leg는 [항공사코드, [항공사명], [세그먼트들...], 출발공항, ...] 형태.
    price_block은 [[None, 가격], 예약토큰] 또는 가격 미확정 시 [[], 예약토큰] 형태.
    """
    try:
        if not (isinstance(x, list) and len(x) == 11):
            return False
        leg, price_block = x[0], x[1]
        if not (isinstance(leg, list) and len(leg) >= 20):
            return False
        if not (isinstance(leg[0], str) and 1 <= len(leg[0]) <= 3):
            return False
        if not (isinstance(leg[2], list) and len(leg[2]) >= 1):
            return False
        if not (isinstance(price_block, list) and len(price_block) == 2):
            return False
        if not (isinstance(price_block[0], list) and len(price_block[0]) in (0, 2)):
            return False
        return True
    except Exception:
        return False


def find_itinerary_lists(obj, path="root", found=None):
    """
    전체 JSON 트리를 순회하면서 '모든 원소가 itinerary 시그니처를 만족하는 리스트'를 찾는다.
    구조 인덱스는 응답마다(가는 편/오는 편 등) 달라질 수 있어 패턴 매칭 방식을 씀.
    """
    if found is None:
        found = []

    if isinstance(obj, list):
        if len(obj) > 0 and all(looks_like_itinerary(item) for item in obj):
            found.append((path, obj))
        else:
            for i, item in enumerate(obj):
                find_itinerary_lists(item, f"{path}[{i}]", found)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            find_itinerary_lists(v, f"{path}.{k}", found)

    return found


def extract_offer(
    itinerary: list, collected_at: str, usd_krw_rate: float | None = None
) -> dict:
    leg = itinerary[0]
    segments = leg[2]
    price_block = itinerary[1][0]
    price_usd = price_block[1] if len(price_block) == 2 else None  # 이제 Google이 준 원본
    price_krw = (
        round(price_usd * usd_krw_rate)
        if (price_usd is not None and usd_krw_rate)
        else None
    )

    return {
        "airline_code": leg[0],
        "airline_name": leg[1][0] if leg[1] else None,
        "origin": leg[3],
        "destination": leg[6],
        "depart_date": ymd_to_str(leg[4]),
        "depart_time": hm_to_str(leg[5]),
        "arrive_date": ymd_to_str(leg[7]),
        "arrive_time": hm_to_str(leg[8]),
        "duration_minutes": leg[9],
        "stops": len(segments) - 1,
        "price_krw": price_krw,
        "price_usd": price_usd,
        "co2_grams": segments[0][31] if len(segments[0]) > 31 else None,
        "co2_vs_avg_pct": leg[22][3] if (len(leg) > 22 and leg[22]) else None,
        "collected_at": collected_at,  # 이 가격을 관측한 시점 (UTC ISO). "며칠 전에 사는 게 싼가" 분석의 핵심.
        "segments": [
            {
                "flight_number": f"{seg[22][0]}{seg[22][1]}" if seg[22] else None,
                "operating_carrier": seg[15][0][3] if seg[15] else None,
                "origin": seg[3],
                "destination": seg[6],
                "depart_time": hm_to_str(seg[8]),
                "arrive_time": hm_to_str(seg[10]),
                "duration_minutes": seg[11],
                "aircraft": seg[17],
                "seat_pitch": seg[30] if len(seg) > 30 else None,
            }
            for seg in segments
        ],
    }


def build_offers(
    chunks: list[dict], collected_at: str | None = None, usd_krw_rate: float | None = None
) -> list[dict]:
    """response.json에 해당하는 chunks 구조에서 offer 목록을 뽑고 중복 제거.

    각 offer는 (origin, destination, depart_date) 자체가 '한 방향 항공편'의 라벨이라
    별도로 outbound/return을 구분해서 태깅할 필요가 없다. 왕복 검색 한 번으로
    양쪽 방향 leg가 모두 이 리스트에 섞여 나온다.

    usd_krw_rate가 주어지면 각 offer에 price_usd(환산가)도 함께 채운다.
    """
    collected_at = collected_at or datetime.now(timezone.utc).isoformat()
    itinerary_lists = find_itinerary_lists(chunks)

    offers = []
    seen = set()
    for path, lst in itinerary_lists:
        for it in lst:
            offer = extract_offer(it, collected_at, usd_krw_rate)
            key = (
                offer["airline_code"],
                offer["depart_date"],
                offer["depart_time"],
                offer["origin"],
                offer["destination"],
                offer["price_krw"],
            )
            if key in seen:
                continue
            seen.add(key)
            offers.append(offer)

    return offers


# ── 유틸 함수 ────────────────────────────────────────────────────────────

_JSON_START_CHARS = ("[", "{")

def _deep_parse_json_strings(obj, _depth=0):
    """중첩된 JSON 문자열(문자열 안에 또 JSON이 인코딩된 경우)을 재귀적으로 실제
    파이썬 구조(list/dict)로 풀어준다. 예: '"[[1,2],3]"' -> [[1,2],3]"""
    if _depth > 12:
        return obj
    if isinstance(obj, str):
        s = obj.strip()
        if s[:1] in _JSON_START_CHARS:
            try:
                parsed = json.loads(s)
            except json.JSONDecodeError:
                return obj
            return _deep_parse_json_strings(parsed, _depth + 1)
        return obj
    if isinstance(obj, list):
        return [_deep_parse_json_strings(v, _depth + 1) for v in obj]
    if isinstance(obj, dict):
        return {k: _deep_parse_json_strings(v, _depth + 1) for k, v in obj.items()}
    return obj


def parse_batchexecute(raw_bytes: bytes) -> list[dict]:
    text = raw_bytes.decode("utf-8", errors="strict")
    if text.startswith(")]}'"):
        first_nl = text.find("\n")
        text = text[first_nl + 1:] if first_nl != -1 else ""

    decoder = json.JSONDecoder()
    chunks = []
    pos, n = 0, len(text)

    while pos < n:
        while pos < n and text[pos] in ("\n", "\r"):
            pos += 1
        if pos >= n:
            break

        nl = text.find("\n", pos)
        if nl == -1:
            break
        header = text[pos:nl].strip()
        if not header.isdigit():
            break
        pos = nl + 1

        try:
            data, end = decoder.raw_decode(text, pos)
        except json.JSONDecodeError:
            break

        chunks.append({"declared_length": int(header), "data": _deep_parse_json_strings(data)})
        pos = end

    return chunks


# ── 초기 HTML에 SSR로 박혀있는 데이터 파싱 ──────────────────────────────
#
# 실측 결과: Google Flights는 첫 페이지 로드 시 검색 결과를
# AF_initDataCallback({key:'ds:N', ..., data:[...]}) 형태로 HTML에 직접
# 심어서 보낸다. GetShoppingResults XHR은 필터 변경/추가 로드 등
# *후속* 상호작용에서만 발생하므로, 첫 결과를 얻으려면 이 SSR 데이터를
# 직접 파싱해야 한다.

def _extract_bracket_literal(text: str, start: int) -> str | None:
    """text[start]가 '[' 라고 가정하고, 문자열 리터럴 안의 대괄호는 무시하면서
    짝이 맞는 ']'까지 잘라 반환한다."""
    depth = 0
    i = start
    in_str = False
    esc = False
    quote = None
    n = len(text)
    while i < n:
        c = text[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == quote:
                in_str = False
        else:
            if c in ("'", '"'):
                in_str = True
                quote = c
            elif c == "[":
                depth += 1
            elif c == "]":
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
        i += 1
    return None


def extract_af_init_data(html: str) -> dict[str, list]:
    """HTML 안의 모든 AF_initDataCallback({key:'ds:N', data:[...]}) 블록을
    찾아서 {key: parsed_data} 딕셔너리로 반환한다."""
    result: dict[str, list] = {}
    for m in re.finditer(r"AF_initDataCallback\(\{key:\s*'([^']+)'", html):
        key = m.group(1)
        try:
            data_pos = html.index("data:", m.end())
        except ValueError:
            continue
        bracket_start = html.find("[", data_pos)
        if bracket_start == -1 or bracket_start - data_pos > 20:
            continue  # data: 바로 뒤에 '['가 없으면 (data:function(){...} 형태 등) 스킵
        literal = _extract_bracket_literal(html, bracket_start)
        if literal is None:
            continue
        try:
            result[key] = json.loads(literal)
        except json.JSONDecodeError:
            continue
    return result


def build_offers_from_html(
    html: str, collected_at: str | None = None, usd_krw_rate: float | None = None
) -> list[dict]:
    """페이지 HTML에 SSR로 박혀있는 모든 ds:N 블록을 훑어서 offer를 뽑는다.
    어떤 ds 인덱스에 결과가 들어오는지는 세션마다 달라질 수 있어 전부 훑는다."""
    all_offers: list[dict] = []
    for key, data in extract_af_init_data(html).items():
        offers = build_offers(data, collected_at=collected_at, usd_krw_rate=usd_krw_rate)
        all_offers.extend(offers)

    # ds:N 블록 간에도 같은 itinerary가 중복으로 잡힐 수 있으니 한 번 더 dedup
    seen = set()
    deduped = []
    for o in all_offers:
        key = (o["airline_code"], o["depart_date"], o["depart_time"],
               o["origin"], o["destination"], o["price_krw"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(o)
    return deduped


async def wait_for_network_quiet(
    last_activity_ref: list[float], quiet_seconds: float, max_wait_seconds: float
) -> None:
    """last_activity_ref[0] (마지막 매칭 응답 수신 시각) 기준으로,
    quiet_seconds 동안 새 응답이 없으면 리턴한다. GetShoppingResults가
    한 번이 아니라 여러 번 나뉘어 올 수 있어서, 고정 타임아웃 대신
    '조용해질 때까지' 기다리는 방식으로 바꾼 것."""
    loop = asyncio.get_running_loop()
    start = loop.time()
    while True:
        now = loop.time()
        if now - last_activity_ref[0] >= quiet_seconds:
            return
        if now - start >= max_wait_seconds:
            print(f"[!] 네트워크 quiet 대기 {max_wait_seconds}s 초과, 강제 진행")
            return
        await asyncio.sleep(0.5)


async def scroll_through_results(
    page,
    last_activity_ref: list[float],
    rounds: int = 6,
    pause_seconds: float = 0.6,
    quiet_seconds: float = 3.0,
    max_wait_seconds: float = 20.0,
) -> None:
    """결과 리스트를 아래로 여러 번 스크롤한다.

    'Other flights' 하단 항목들은 뷰포트에 들어와야만 가격 조회가 지연 트리거되는
    것으로 보여서(스크롤을 안 하면 price_block이 계속 빈 상태로 남음), 페이지
    로드/탭 전환 직후 이 함수로 스크롤을 흘려보내 해당 XHR들이 발생하도록 만든다.
    새로 발생하는 응답은 이미 등록된 handle_response 리스너가 자동으로 잡아서
    response_NNN.txt/json에 저장하고 offers_store에 병합한다.
    """
    for _ in range(rounds):
        await page.mouse.wheel(0, 1200)
        await asyncio.sleep(pause_seconds)
    await wait_for_network_quiet(last_activity_ref, quiet_seconds=quiet_seconds, max_wait_seconds=max_wait_seconds)


# ── 메인 로직 ────────────────────────────────────────────────────────────

async def main() -> None:
    parser = argparse.ArgumentParser(description="Google Flights 텍스트 검색 크롤러")
    parser.add_argument("--origin", required=True, help="출발지 (예: Seoul, ICN)")
    parser.add_argument("--destination", required=True, help="도착지 (예: Qingdao, TAO)")
    parser.add_argument("--depart", required=True, help="출발일 YYYY-MM-DD")
    parser.add_argument("--return-date", default=None, help="귀국일 YYYY-MM-DD (편도면 생략)")
    args = parser.parse_args()

    target_url = build_search_url(args.origin, args.destination, args.depart, args.return_date)
    collected_at = datetime.now(timezone.utc).isoformat()

    try:
        usd_krw_rate = fetch_usd_krw_rate()
    except Exception as e:
        print(f"[!] 환율 조회 실패, price_usd는 저장되지 않습니다: {e}")
        usd_krw_rate = None

    # OUTPUT_DIR.mkdir(exist_ok=True)
    db.init_db()

    search_run_id = db.create_search_run(
        query_origin=args.origin,
        query_destination=args.destination,
        query_depart_date=args.depart,
        query_return_date=args.return_date,
        target_url=target_url,
        run_at=collected_at,
        usd_krw_rate=usd_krw_rate,
    )

    # 같은 itinerary가 (가격 미확정 -> 확정) 형태로 여러 번 응답에 나뉘어 올 수 있어서,
    # 응답마다 바로 저장하지 않고 identity 기준으로 메모리에서 병합한 뒤 마지막에 한 번만 저장한다.
    offers_store: dict[tuple, dict] = {}
    loop = asyncio.get_running_loop()
    last_activity = [loop.time()]

    def merge_offer(offer: dict) -> None:
        key = (
            offer["airline_code"], offer["depart_date"], offer["depart_time"],
            offer["origin"], offer["destination"],
        )
        existing = offers_store.get(key)
        if existing is None:
            offers_store[key] = offer
            return
        if existing.get("price_usd") is None and offer.get("price_usd") is not None:
            offers_store[key] = offer
        elif existing.get("price_krw") is None and offer.get("price_krw") is not None:
            offers_store[key] = offer

    def log_all_responses(response: Response) -> None:
        """가격이 우리가 모르는 다른 엔드포인트에서 오는지 확인하기 위한 진단용 로그.
        google.com으로 가는 모든 응답의 URL/상태/컨텐츠타입을 한 줄씩 기록한다."""
        try:
            if "google.com" not in response.url:
                return
            # ct = response.headers.get("content-type", "")
            # with ALL_RESPONSES_LOG_PATH.open("a", encoding="utf-8") as f:
            #     f.write(f"{response.status}\t{ct}\t{response.url}\n")
        except Exception:
            pass

    async def handle_response(response: Response) -> None:
        log_all_responses(response)
        if not TARGET_URL_PATTERN.search(response.url):
            return
        try:
            body_bytes = await response.body()
        except Exception as e:
            print(f"[!] 응답 바디를 읽지 못했습니다 ({response.url}): {e}")
            return

        # txt_path, json_path = _next_response_paths()
        # txt_path.write_bytes(body_bytes)

        last_activity[0] = loop.time()
        chunks = parse_batchexecute(body_bytes)

        # json_path.write_text(
        #     json.dumps(chunks, ensure_ascii=False, indent=2),
        #     encoding="utf-8",
        # )
        # print(f"[+] XHR 캡처 저장: {txt_path.name} / {json_path.name}")

        try:
            offers = build_offers(chunks, collected_at=collected_at, usd_krw_rate=usd_krw_rate)
        except Exception as e:
            print(f"[!] offer 파싱 오류(XHR): {e}")
            offers = []
        for o in offers:
            merge_offer(o)
        if offers:
            print(f"[+] XHR 응답 수신: {len(offers)}개 offer 병합 (누적 {len(offers_store)}개)")

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",    # /dev/shm 용량이 작은 환경에서 크래시 방지
                "--disable-gpu",              # Xvfb 소프트웨어 렌더링과 GPU 가속을 같이 쓰면 오히려 불안정
                "--disk-cache-size=52428800", # 디스크 캐시를 50MB로 제한 (장기 실행 시 프로필 폴더 무한 증식 방지)
            ],
        )
        page = await context.new_page()
        page.on("response", lambda r: asyncio.ensure_future(handle_response(r)))

        print(f"[*] 페이지 접속 중: {target_url}")
        await page.goto(target_url, wait_until="networkidle", timeout=60_000)
        await wait_for_network_quiet(last_activity, quiet_seconds=3.0, max_wait_seconds=25.0)

        print("[*] Other flights 가격 지연 조회를 위해 스크롤 진행 중...")
        await scroll_through_results(page, last_activity)

        html = await page.content()

        # html_txt_path, html_json_path = _next_response_paths()
        # html_txt_path.write_text(html, encoding="utf-8")
        # af_init_data = extract_af_init_data(html)
        # html_json_path.write_text(
        #     json.dumps(af_init_data, ensure_ascii=False, indent=2),
        #     encoding="utf-8",
        # )
        # print(f"[+] 초기 HTML 캡처 저장: {html_txt_path.name} / {html_json_path.name}")

        try:
            html_offers = build_offers_from_html(html, collected_at=collected_at, usd_krw_rate=usd_krw_rate)
        except Exception as e:
            print(f"[!] offer 파싱 오류(HTML): {e}")
            html_offers = []
        for o in html_offers:
            merge_offer(o)
        print(f"[+] 초기 HTML(Best) 병합 완료 (누적 {len(offers_store)}개)")

        # Best 탭만으로는 노출되지 않는 항공편이 Cheapest 탭에만 나오는 경우가 있어서,
        # sort-by 옵션 없이 항상 두 탭을 다 훑는다.
        try:
            cheapest_tab = page.get_by_role("tab", name=re.compile("Cheapest")).first
            await cheapest_tab.wait_for(state="visible", timeout=10_000)
            last_activity[0] = loop.time()
            await cheapest_tab.click(timeout=10_000)

            # 탭 전환도 응답이 한 번에 안 끝날 수 있으므로 quiet 대기
            await wait_for_network_quiet(last_activity, quiet_seconds=3.0, max_wait_seconds=25.0)

            print("[*] Other flights 가격 지연 조회를 위해 스크롤 진행 중... (Cheapest)")
            await scroll_through_results(page, last_activity)

            html_after = await page.content()

            # html_after_txt_path, html_after_json_path = _next_response_paths()
            # html_after_txt_path.write_text(html_after, encoding="utf-8")
            # af_init_data_after = extract_af_init_data(html_after)
            # html_after_json_path.write_text(
                # json.dumps(af_init_data_after, ensure_ascii=False, indent=2),
                # encoding="utf-8",
            # )
            # print(f"[+] Cheapest HTML 캡처 저장: {html_after_txt_path.name} / {html_after_json_path.name}")

            try:
                html_offers_after = build_offers_from_html(
                    html_after, collected_at=collected_at, usd_krw_rate=usd_krw_rate
                )
            except Exception as e:
                print(f"[!] offer 파싱 오류(HTML, Cheapest): {e}")
                html_offers_after = []
            for o in html_offers_after:
                merge_offer(o)
            print(f"[+] Cheapest 탭 병합 완료 (누적 {len(offers_store)}개)")
        except Exception as e:
            print(f"[!] Cheapest 탭 클릭 실패: {type(e).__name__}: {e}")

        await context.close()

    final_offers = list(offers_store.values())
    priced_offers = [o for o in final_offers if o["price_usd"] is not None or o["price_krw"] is not None]
    skipped_no_price = len(final_offers) - len(priced_offers)

    # DATA_PATH.write_text(
    #     json.dumps(final_offers, ensure_ascii=False, indent=2),
    #     encoding="utf-8",
    # )

    total_saved = db.save_offers(priced_offers, search_run_id=search_run_id)

    if total_saved == 0:
        print("[!] 이번 실행에서 저장된 항공권이 0건입니다. "
              "캡차/동의 화면으로 리다이렉트됐을 수 있으니 headless=False로 한 번 더 확인해보세요.")
    else:
        print(f"[*] 총 {total_saved}행 저장 완료 (search_run_id={search_run_id}, "
              f"가격 미확정으로 제외된 항목 {skipped_no_price}건)")


if __name__ == "__main__":
    asyncio.run(main())