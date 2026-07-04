"""
routes + tracked_dates 테이블을 기준으로 app.py를 반복 실행하는 상시 스케줄러.

확장 설계 원칙:
- 추적할 노선을 코드에 하드코딩하지 않고 routes 테이블에서 매 SYNC_INTERVAL_SECONDS
  마다 다시 읽는다. manage_routes.py로 노선을 추가하면 재시작 없이도 자동 반영된다.
- 노선이 늘어나 하루 처리 용량을 넘기면(=일부 날짜가 STALE_HOURS 넘게 안 갱신되면)
  경고를 출력해서, 처리 못 하고 있다는 사실이 로그에 조용히 묻히지 않게 한다.
"""

import random
import subprocess
import sys
import time
from pathlib import Path

import src.db as db

APP_PATH = Path(__file__).parent / "app.py"
HORIZON_DAYS = 365
DAY_SECONDS = 24 * 3600
JITTER_SECONDS = 20
MIN_SLEEP_SECONDS = 5.0
SUBPROCESS_TIMEOUT = 300
SYNC_INTERVAL_SECONDS = 3600     # routes/날짜 목록을 다시 확인하는 주기 (1시간)
STALE_HOURS = 30.0                # 이보다 오래 안 갱신되면 "밀렸다"고 판단
STALE_WARN_RATIO = 0.10           # 활성 대상의 10% 이상이 밀리면 경고


def run_once(origin: str, destination: str, flight_date: str) -> bool:
    proc = subprocess.run(
        [sys.executable, str(APP_PATH),
         "--origin", origin, "--destination", destination, "--depart", flight_date],
        cwd=APP_PATH.parent,
        capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT,
    )
    if proc.stdout:
        print(proc.stdout.strip())
    if proc.returncode != 0:
        print(f"[!] app.py 비정상 종료 (returncode={proc.returncode}): "
              f"{origin}->{destination} {flight_date}")
        if proc.stderr:
            print(proc.stderr[-2000:])
        return False
    return True


def resync(routes: list[tuple[str, str]]) -> None:
    for origin, destination in routes:
        db.sync_tracked_dates(origin, destination, horizon_days=HORIZON_DAYS)

    active_count = db.count_active_tracked_dates()
    stale_count = db.count_stale_tracked_dates(stale_hours=STALE_HOURS)
    print(f"[*] 동기화 완료. 노선 {len(routes)}개(양방향 포함), "
          f"활성 추적 대상 {active_count}건, 지연된 대상 {stale_count}건")

    if active_count > 0 and stale_count / active_count > STALE_WARN_RATIO:
        print(f"[!!] 경고: 활성 대상의 {stale_count / active_count:.0%}가 "
              f"{STALE_HOURS:.0f}시간 넘게 갱신되지 못했습니다. "
              f"노선을 줄이거나 건당 처리 시간을 단축하세요 — 지금 페이스로는 "
              f"용량 초과 상태일 수 있습니다.")


def main() -> None:
    db.init_db()
    db.init_routes_table()
    db.init_tracked_dates_table()

    last_sync_at = 0.0

    while True:
        now = time.monotonic()
        if now - last_sync_at >= SYNC_INTERVAL_SECONDS:
            routes = db.get_active_routes()
            if not routes:
                print("[!] 등록된 노선이 없습니다. manage_routes.py add로 노선을 추가하세요.")
            resync(routes)
            last_sync_at = now

        target = db.get_next_tracked_date()
        if target is None:
            print("[!] 추적 대상이 없습니다. 60초 후 재확인.")
            time.sleep(60)
            continue

        active_count = db.count_active_tracked_dates()
        target_cycle = DAY_SECONDS / max(active_count, 1)

        t0 = time.monotonic()
        print(f"[*] 수집 시작: {target['origin']}->{target['destination']} {target['flight_date']}")
        run_once(target["origin"], target["destination"], target["flight_date"])
        db.mark_collected(target["id"])
        elapsed = time.monotonic() - t0

        remaining = target_cycle - elapsed
        sleep_for = max(MIN_SLEEP_SECONDS, remaining + random.uniform(-JITTER_SECONDS, JITTER_SECONDS))
        print(f"[*] 소요 {elapsed:.0f}s / 다음까지 {sleep_for:.0f}s 대기 "
              f"(목표 주기 {target_cycle:.0f}s, 활성 {active_count}건)")
        time.sleep(sleep_for)


if __name__ == "__main__":
    main()