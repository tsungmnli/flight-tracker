"""
편도(leg) 단위로 항공권 가격을 누적 저장하는 MySQL 헬퍼.
"""

import os
from datetime import date, datetime, timezone, timedelta

import mysql.connector

KST = timezone(timedelta(hours=9))

# 접속 정보는 코드에 직접 적지 않고 환경변수에서 읽는다.
# (환경변수를 안 넣고 그냥 실행하면 아래 기본값으로 시도한다 — 테스트용.)
DB_CONFIG = {
    "host": os.environ.get("FLIGHTS_DB_HOST", "127.0.0.1"),
    "user": os.environ.get("FLIGHTS_DB_USER", "flights_app"),
    "password": os.environ.get("FLIGHTS_DB_PASSWORD", ""),
    "database": os.environ.get("FLIGHTS_DB_NAME", "flights"),
}


def get_conn():
    return mysql.connector.connect(**DB_CONFIG)


def _column_exists(conn, table: str, column: str) -> bool:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT COUNT(*) FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND COLUMN_NAME = %s
        """,
        (DB_CONFIG["database"], table, column),
    )
    (count,) = cur.fetchone()
    cur.close()
    return count > 0


def _index_exists(conn, table: str, index_name: str) -> bool:
    """MySQL에는 'CREATE INDEX IF NOT EXISTS' 문법이 없어서, 만들기 전에
    이미 있는지 직접 확인하는 함수를 따로 둔다."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT COUNT(*) FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND INDEX_NAME = %s
        """,
        (DB_CONFIG["database"], table, index_name),
    )
    (count,) = cur.fetchone()
    cur.close()
    return count > 0


def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS search_runs (
            id INT AUTO_INCREMENT PRIMARY KEY,
            run_at VARCHAR(40) NOT NULL,
            query_origin VARCHAR(64) NOT NULL,
            query_destination VARCHAR(64) NOT NULL,
            query_depart_date VARCHAR(10) NOT NULL,
            query_return_date VARCHAR(10),
            target_url TEXT,
            usd_krw_rate DOUBLE
        ) ENGINE=InnoDB
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS flight_prices (
            id INT AUTO_INCREMENT PRIMARY KEY,
            search_run_id INT NOT NULL,
            origin VARCHAR(8) NOT NULL,
            destination VARCHAR(8) NOT NULL,
            depart_date VARCHAR(10) NOT NULL,
            collected_at VARCHAR(40) NOT NULL,
            days_before_departure INT NOT NULL,
            depart_time VARCHAR(8),
            arrive_date VARCHAR(10),
            arrive_time VARCHAR(8),
            airline_code VARCHAR(8),
            airline_name VARCHAR(128),
            duration_minutes INT,
            stops INT,
            price_krw INT,
            price_usd DOUBLE,
            co2_grams INT,
            co2_vs_avg_pct INT,
            FOREIGN KEY (search_run_id) REFERENCES search_runs(id)
        ) ENGINE=InnoDB
    """)

    if not _column_exists(conn, "flight_prices", "price_usd"):
        cur.execute("ALTER TABLE flight_prices ADD COLUMN price_usd DOUBLE")
    if not _column_exists(conn, "search_runs", "usd_krw_rate"):
        cur.execute("ALTER TABLE search_runs ADD COLUMN usd_krw_rate DOUBLE")

    if not _index_exists(conn, "flight_prices", "idx_route_date"):
        cur.execute("CREATE INDEX idx_route_date ON flight_prices (origin, destination, depart_date)")
    if not _index_exists(conn, "flight_prices", "idx_search_run"):
        cur.execute("CREATE INDEX idx_search_run ON flight_prices (search_run_id)")
    if not _index_exists(conn, "flight_prices", "idx_dedupe"):
        cur.execute("""
            CREATE UNIQUE INDEX idx_dedupe
            ON flight_prices (
                search_run_id, origin, destination, depart_date,
                depart_time, arrive_date, arrive_time,
                airline_code, price_krw
            )
        """)

    conn.commit()
    cur.close()
    conn.close()


# ── search_runs ──────────────────────────────────────────────────────────

def create_search_run(
    query_origin: str,
    query_destination: str,
    query_depart_date: str,
    query_return_date: str | None,
    target_url: str,
    run_at: str | None = None,
    usd_krw_rate: float | None = None,
) -> int:
    run_at = run_at or datetime.now(timezone.utc).isoformat()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO search_runs
            (run_at, query_origin, query_destination, query_depart_date, query_return_date,
             target_url, usd_krw_rate)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (run_at, query_origin, query_destination, query_depart_date, query_return_date,
         target_url, usd_krw_rate),
    )
    run_id = cur.lastrowid
    conn.commit()
    cur.close()
    conn.close()
    return run_id


# ── 저장 ─────────────────────────────────────────────────────────────────

def _days_before_departure(depart_date: str, collected_at: str) -> int:
    d = date.fromisoformat(depart_date)
    c = datetime.fromisoformat(collected_at).astimezone(KST).date()
    return (d - c).days


def save_offers(offers: list[dict], search_run_id: int) -> int:
    if not offers:
        return 0

    conn = get_conn()
    cur = conn.cursor()
    inserted = 0

    for o in offers:
        try:
            dbd = _days_before_departure(o["depart_date"], o["collected_at"])
        except Exception:
            dbd = None

        row = {
            "search_run_id": search_run_id,
            "origin": o.get("origin"),
            "destination": o.get("destination"),
            "depart_date": o.get("depart_date"),
            "collected_at": o.get("collected_at"),
            "days_before_departure": dbd,
            "depart_time": o.get("depart_time"),
            "arrive_date": o.get("arrive_date"),
            "arrive_time": o.get("arrive_time"),
            "airline_code": o.get("airline_code"),
            "airline_name": o.get("airline_name"),
            "duration_minutes": o.get("duration_minutes"),
            "stops": o.get("stops"),
            "price_krw": o.get("price_krw"),
            "price_usd": o.get("price_usd"),
            "co2_grams": o.get("co2_grams"),
            "co2_vs_avg_pct": o.get("co2_vs_avg_pct"),
        }

        cur.execute(
            """
            INSERT IGNORE INTO flight_prices
                (search_run_id, origin, destination, depart_date, collected_at,
                 days_before_departure, depart_time, arrive_date, arrive_time,
                 airline_code, airline_name, duration_minutes, stops, price_krw, price_usd,
                 co2_grams, co2_vs_avg_pct)
            VALUES
                (%(search_run_id)s, %(origin)s, %(destination)s, %(depart_date)s, %(collected_at)s,
                 %(days_before_departure)s, %(depart_time)s, %(arrive_date)s, %(arrive_time)s,
                 %(airline_code)s, %(airline_name)s, %(duration_minutes)s, %(stops)s, %(price_krw)s, %(price_usd)s,
                 %(co2_grams)s, %(co2_vs_avg_pct)s)
            """,
            row,
        )
        inserted += cur.rowcount if cur.rowcount > 0 else 0

    conn.commit()
    cur.close()
    conn.close()
    return inserted


# ── 조회 ─────────────────────────────────────────────────────────────────

def get_leg_price_history(origin: str, destination: str, depart_date: str) -> list[dict]:
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """
        SELECT collected_at, days_before_departure, price_krw AS min_price_krw,
               airline_code, airline_name
        FROM (
            SELECT t.*,
                   ROW_NUMBER() OVER (
                       PARTITION BY collected_at
                       ORDER BY price_krw ASC
                   ) AS rn
            FROM flight_prices t
            WHERE origin = %s AND destination = %s AND depart_date = %s
              AND price_krw IS NOT NULL
        ) ranked
        WHERE rn = 1
        ORDER BY collected_at
        """,
        (origin, destination, depart_date),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def get_roundtrip_price_history(
    outbound_origin: str,
    outbound_destination: str,
    outbound_date: str,
    return_origin: str,
    return_destination: str,
    return_date: str,
) -> list[dict]:
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """
        WITH outbound_min AS (
            SELECT search_run_id, collected_at, days_before_departure,
                   MIN(price_krw) AS out_price
            FROM flight_prices
            WHERE origin = %s AND destination = %s AND depart_date = %s
              AND price_krw IS NOT NULL
            GROUP BY search_run_id
        ),
        return_min AS (
            SELECT search_run_id, MIN(price_krw) AS ret_price
            FROM flight_prices
            WHERE origin = %s AND destination = %s AND depart_date = %s
              AND price_krw IS NOT NULL
            GROUP BY search_run_id
        )
        SELECT
            o.collected_at,
            o.days_before_departure,
            o.out_price,
            r.ret_price,
            (o.out_price + r.ret_price) AS total_price_krw
        FROM outbound_min o
        JOIN return_min r ON r.search_run_id = o.search_run_id
        ORDER BY o.collected_at
        """,
        (
            outbound_origin, outbound_destination, outbound_date,
            return_origin, return_destination, return_date,
        ),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


# ── 추적 노선 (routes) ───────────────────────────────────────────────────

def init_routes_table():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS routes (
            id INT AUTO_INCREMENT PRIMARY KEY,
            origin VARCHAR(8) NOT NULL,
            destination VARCHAR(8) NOT NULL,
            active TINYINT NOT NULL DEFAULT 1,
            added_at VARCHAR(40) NOT NULL
        ) ENGINE=InnoDB
    """)
    if not _index_exists(conn, "routes", "idx_routes_unique"):
        cur.execute("CREATE UNIQUE INDEX idx_routes_unique ON routes (origin, destination)")
    conn.commit()
    cur.close()
    conn.close()


def add_route_pair(airport_a: str, airport_b: str) -> None:
    now_iso = datetime.now(timezone.utc).isoformat()
    conn = get_conn()
    cur = conn.cursor()
    for origin, destination in [(airport_a, airport_b), (airport_b, airport_a)]:
        cur.execute(
            """
            INSERT INTO routes (origin, destination, active, added_at)
            VALUES (%s, %s, 1, %s)
            ON DUPLICATE KEY UPDATE active = 1
            """,
            (origin, destination, now_iso),
        )
    conn.commit()
    cur.close()
    conn.close()


def deactivate_route(origin: str, destination: str) -> None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE routes SET active = 0 WHERE origin = %s AND destination = %s",
        (origin, destination),
    )
    conn.commit()
    cur.close()
    conn.close()


def get_active_routes() -> list[tuple[str, str]]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT origin, destination FROM routes WHERE active = 1")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [(r[0], r[1]) for r in rows]


def get_all_routes() -> list[dict]:
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM routes ORDER BY added_at")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


# ── 추적 스케줄 (tracked_dates) ──────────────────────────────────────────

def init_tracked_dates_table():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tracked_dates (
            id INT AUTO_INCREMENT PRIMARY KEY,
            origin VARCHAR(8) NOT NULL,
            destination VARCHAR(8) NOT NULL,
            flight_date VARCHAR(10) NOT NULL,
            first_tracked_at VARCHAR(40) NOT NULL,
            last_collected_at VARCHAR(40),
            active TINYINT NOT NULL DEFAULT 1
        ) ENGINE=InnoDB
    """)
    if not _index_exists(conn, "tracked_dates", "idx_tracked_unique"):
        cur.execute("CREATE UNIQUE INDEX idx_tracked_unique ON tracked_dates (origin, destination, flight_date)")
    conn.commit()
    cur.close()
    conn.close()


def sync_tracked_dates(origin: str, destination: str, horizon_days: int = 365) -> None:
    today = datetime.now(KST).date()
    now_iso = datetime.now(timezone.utc).isoformat()

    conn = get_conn()
    cur = conn.cursor()
    for offset in range(horizon_days + 1):
        flight_date = (today + timedelta(days=offset)).isoformat()
        cur.execute(
            """
            INSERT IGNORE INTO tracked_dates
                (origin, destination, flight_date, first_tracked_at, active)
            VALUES (%s, %s, %s, %s, 1)
            """,
            (origin, destination, flight_date, now_iso),
        )
    cur.execute(
        """
        UPDATE tracked_dates SET active = 0
        WHERE origin = %s AND destination = %s AND flight_date < %s
        """,
        (origin, destination, today.isoformat()),
    )
    conn.commit()
    cur.close()
    conn.close()


def get_next_tracked_date() -> dict | None:
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """
        SELECT * FROM tracked_dates
        WHERE active = 1
        ORDER BY (last_collected_at IS NOT NULL), last_collected_at ASC
        LIMIT 1
        """
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row


def count_active_tracked_dates() -> int:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM tracked_dates WHERE active = 1")
    (n,) = cur.fetchone()
    cur.close()
    conn.close()
    return n


def mark_collected(tracked_date_id: int, collected_at: str | None = None) -> None:
    collected_at = collected_at or datetime.now(timezone.utc).isoformat()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE tracked_dates SET last_collected_at = %s WHERE id = %s",
        (collected_at, tracked_date_id),
    )
    conn.commit()
    cur.close()
    conn.close()


def count_stale_tracked_dates(stale_hours: float = 30.0) -> int:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=stale_hours)).isoformat()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT COUNT(*) FROM tracked_dates
        WHERE active = 1 AND (last_collected_at IS NULL OR last_collected_at < %s)
        """,
        (cutoff,),
    )
    (n,) = cur.fetchone()
    cur.close()
    conn.close()
    return n


if __name__ == "__main__":
    init_db()
    init_routes_table()
    init_tracked_dates_table()
    print(f"MySQL '{DB_CONFIG['database']}' 데이터베이스에 테이블 생성 완료 "
          f"(host={DB_CONFIG['host']}, user={DB_CONFIG['user']})")