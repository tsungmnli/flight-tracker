"""
추적 노선을 추가/중단/조회하는 커맨드라인 도구.

사용 예:
    python3 manage_routes.py add ICN TAO         # ICN<->TAO 양방향 추적 시작
    python3 manage_routes.py add ICN NRT         # 노선 추가 (기존 노선엔 영향 없음)
    python3 manage_routes.py add-one ICN NRT     # ICN->NRT 한쪽 방향만 추적 시작
    python3 manage_routes.py list                # 현재 등록된 노선 확인
    python3 manage_routes.py deactivate ICN NRT  # NRT 방향만 중단 (이력은 보존)

스케줄러(scheduler.py)는 최대 1시간(SYNC_INTERVAL_SECONDS) 안에 새 노선을 자동으로
반영합니다. 당장 반영하고 싶으면 이 스크립트 실행 직후
`sudo systemctl restart flight-scheduler`로 재시작하세요.
"""

import argparse

import shared.db as db


def main() -> None:
    parser = argparse.ArgumentParser(description="추적 노선 관리")
    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add", help="공항 쌍을 양방향으로 추가")
    p_add.add_argument("airport_a")
    p_add.add_argument("airport_b")
    p_add.add_argument("--horizon-days", type=int, default=365)

    p_add_one = sub.add_parser("add-one", help="origin -> destination 한쪽 방향만 추가")
    p_add_one.add_argument("origin")
    p_add_one.add_argument("destination")
    p_add_one.add_argument("--horizon-days", type=int, default=365)

    sub.add_parser("list", help="등록된 노선 목록 확인")

    p_deactivate = sub.add_parser("deactivate", help="한쪽 방향 추적 중단")
    p_deactivate.add_argument("origin")
    p_deactivate.add_argument("destination")

    args = parser.parse_args()

    db.init_db()
    db.init_routes_table()
    db.init_tracked_dates_table()

    if args.command == "add":
        db.add_route_pair(args.airport_a, args.airport_b)
        for origin, destination in [
            (args.airport_a, args.airport_b),
            (args.airport_b, args.airport_a),
        ]:
            db.sync_tracked_dates(origin, destination, horizon_days=args.horizon_days)
        print(f"[+] {args.airport_a} <-> {args.airport_b} 추적 시작 "
              f"(양방향, {args.horizon_days}일 범위)")
        print("    스케줄러가 실행 중이면 최대 1시간 내 자동 반영됩니다.")

    elif args.command == "add-one":
        db.add_route(args.origin, args.destination)
        db.sync_tracked_dates(args.origin, args.destination, horizon_days=args.horizon_days)
        print(f"[+] {args.origin} -> {args.destination} 추적 시작 "
              f"(단방향, {args.horizon_days}일 범위)")
        print("    스케줄러가 실행 중이면 최대 1시간 내 자동 반영됩니다.")

    elif args.command == "list":
        routes = db.get_all_routes()
        if not routes:
            print("등록된 노선이 없습니다.")
        for r in routes:
            status = "활성" if r["active"] else "중단"
            print(f"  [{status}] {r['origin']} -> {r['destination']}  (등록일: {r['added_at'][:10]})")

    elif args.command == "deactivate":
        db.deactivate_route(args.origin, args.destination)
        print(f"[-] {args.origin} -> {args.destination} 추적 중단 (기존 데이터는 보존됨)")


if __name__ == "__main__":
    main()