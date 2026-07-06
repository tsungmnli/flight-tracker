# API Service

수집된 항공권 가격/환율/유가 데이터를 조회·추천하는 FastAPI 서버입니다.

전체 프로젝트 개요는 [README](../../README.md) 참고.

## 실행

```bash
docker compose up -d --build api
docker compose logs -f api
```

## Swagger UI (대화형 문서)

FastAPI는 실행 중 자동으로 대화형 API 문서를 만들어줍니다. 브라우저에서:

```
http://<홈서버IP>:8000/docs
```

아래 명세와 항상 동일한 최신 상태로 유지되므로, 실제로 요청을 테스트해볼 땐 이쪽을 쓰는 게 더 편합니다.

## 헬스 체크

```bash
curl http://127.0.0.1:8000/health
```

---

## API 명세 (v1)

### 공통 사항

- 모든 엔드포인트는 `/v1` 접두사를 붙인다. (`GET /v1/routes/available` 등)
- 응답은 JSON. 통화가 관련된 값은 `currency` 쿼리 파라미터로 `KRW`(기본값) 또는 `USD` 선택.
- 정규화가 관련된 엔드포인트는 `normalize_by` 파라미터로 `none`(기본값) / `oil_price` / `usd_krw` 선택.
  - **계산 방식**: "그때 가격이 오늘 기준 유가/환율이었다면 얼마였을지"로 환산한다.
    ```
    price_normalized_oil    = 그때_가격 × (오늘_유가 / 그때_유가)
    price_normalized_usd_krw = 그때_가격(KRW) / 오늘_환율
    ```
    예: 유가가 그때 더 비쌌다면(`그때_유가` > `오늘_유가`) 보정값이 실제 가격보다 낮아진다 — "그때는 유가가 비싼데도 이 가격이었으니, 지금 유가 기준으로 치면 사실 더 싼 셈"이라는 의미.
  - `normalize_by`를 `none`이 아닌 값으로 요청하면, 응답 최상위에 `"experimental": true`가 함께 내려온다. 정규화 공식이 실제로 유의미한 차이를 만드는지 아직 충분한 기간(유가가 오르내리는 구간 포함 최소 90일)의 데이터로 검증되지 않았기 때문이다. 검증 후 이 플래그는 제거될 예정.
- 목록을 반환하는 엔드포인트는 `limit`(기본 20, 최대 100), `offset`(기본 0)을 지원한다.
- 사용자 대상 조회(1~5번 그룹)는 인증 없이 홈 네트워크 안에서 사용. 관리용(6번 그룹)은 `X-API-Key` 헤더 필요.
- 공통 에러 형식:
  ```json
  { "error": { "code": "ROUTE_NOT_FOUND", "message": "..." } }
  ```

---

### 1. Available Routes API

#### `GET /v1/routes/available`
현재 추적 중이고 실제 가격 데이터가 1건 이상 있는 노선만 반환한다. (추적 시작만 하고 데이터가 아직 없는 노선은 제외 — 검색/추천 대상에서 걸러내기 위함)

**Query**
| 이름 | 타입 | 설명 |
|---|---|---|
| `origin` | string, optional | 특정 출발지만 필터링 |

**Response 예시**
```json
{
  "routes": [
    {
      "origin": "ICN",
      "destination": "NRT",
      "active": true,
      "first_price_collected_at": "2026-05-01T02:00:00Z",
      "last_price_collected_at": "2026-07-05T14:00:00Z"
    }
  ]
}
```

---

### 2. Itinerary Search API

#### `GET /v1/itineraries/search`
사용자가 가는 날/오는 날을 지정해 검색하면, 편도 최저가 하나만 주는 게 아니라 **여러 조합을 점수 순으로 나열**한다 (네이버 지도의 경로 추천처럼).

**정렬 기준 (`sort_by`)**
| 값 | 설명 |
|---|---|
| `cheapest` | 총 가격이 낮은 순 |
| `best_schedule` | 이른 시간 출발 + 늦은 시간 귀국 + 경유 적음 등 "일정 활용도"가 좋은 순 |
| `balanced` (기본값) | 가격과 일정 점수를 함께 반영한 종합 점수 순 |

**점수 계산 방식**
- `price_score` (0~100): 이번 검색 결과 안에서 최저가=100, 최고가=0이 되도록 상대 환산
- `schedule_score` (0~100): 아래 4개 요소를 동일 비중(각 25%)으로 평균
  - 출발시간: 이른 오전(06:00~11:00)일수록 높음
  - 귀국 도착시간: 오후~저녁(15:00~21:00)일수록 높음
  - 경유: 직항 100 / 1회 70 / 2회 이상 40
  - 소요시간: 이번 검색 결과 중 최단시간 대비 상대 점수
- `balanced` 종합점수 = `price_score × price_weight + schedule_score × (1 - price_weight)`
  - `price_weight` 기본값 `0.6` (가격에 조금 더 비중). 쿼리 파라미터로 사용자가 직접 조정 가능.

**Query**
| 이름 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `origin` | string | ✅ | 출발지 |
| `destination` | string | ✅ | 도착지 |
| `depart_date` | string (YYYY-MM-DD) | ✅ | 가는 날 |
| `return_date` | string (YYYY-MM-DD) | | 오는 날 (없으면 편도 검색) |
| `sort_by` | cheapest\|best_schedule\|balanced | | 기본 balanced |
| `price_weight` | float (0~1) | | `balanced`일 때만 적용, 기본 0.6 |
| `currency` | KRW\|USD | | 기본 KRW |
| `normalize_by` | none\|oil_price\|usd_krw | | 기본 none |
| `limit`, `offset` | int | | 페이지네이션 (기본 20) |

**Response 예시**
```json
{
  "depart_date": "2026-11-21",
  "return_date": "2026-11-24",
  "sort_by": "balanced",
  "total_results": 34,
  "itineraries": [
    {
      "rank": 1,
      "score": 92.4,
      "score_breakdown": { "price_score": 88.0, "schedule_score": 95.0 },
      "outbound": {
        "airline_name": "Asiana Airlines",
        "depart_time": "09:20",
        "arrive_time": "12:10",
        "stops": 0,
        "price": 185000,
        "price_normalized": 179300
      },
      "inbound": {
        "airline_name": "Asiana Airlines",
        "depart_time": "18:40",
        "arrive_time": "21:05",
        "stops": 0,
        "price": 172000,
        "price_normalized": 168800
      },
      "total_price": 357000,
      "total_price_normalized": 348100
    }
  ]
}
```
> 주의: `total_price`는 편도 두 건의 조합 합산이며, 실제 항공사가 판매하는 왕복 결합 운임과는 다를 수 있다.
> `score_breakdown`은 왜 이 순위인지 사용자에게 설명하기 위한 참고용 필드.

---

### 3. Flight Detail / Price Trend API

#### `GET /v1/flights/trend`
특정 노선·출발일 하나를 고정하고, 조회 시점(`collected_at`)에 따른 가격 변화를 반환한다. 그래프의 원본 데이터.

**Query**
| 이름 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `origin` | string | ✅ | |
| `destination` | string | ✅ | |
| `depart_date` | string (YYYY-MM-DD) | ✅ | 고정할 출발일 |
| `currency` | KRW\|USD | | 기본 KRW |
| `normalize_by` | none\|oil_price\|usd_krw | | 기본 none |

**Response 예시**
```json
{
  "origin": "ICN",
  "destination": "NRT",
  "depart_date": "2026-11-21",
  "trend": [
    {
      "collected_at": "2026-10-01T02:00:00Z",
      "days_before_departure": 51,
      "price": 210000,
      "price_normalized": 205400,
      "oil_price_usd": 82.3,
      "krw_usd_rate": 1362.5
    },
    {
      "collected_at": "2026-11-01T02:00:00Z",
      "days_before_departure": 20,
      "price": 195000,
      "price_normalized": 191200,
      "oil_price_usd": 80.1,
      "krw_usd_rate": 1358.0
    }
  ],
  "data_gaps": [
    { "from": "2026-10-15T00:00:00Z", "to": "2026-10-17T00:00:00Z", "reason": "collection_failed" }
  ],
  "cheapest_point": {
    "collected_at": "2026-11-01T02:00:00Z",
    "days_before_departure": 20,
    "price": 195000
  },
  "all_time_low": {
    "price": 178000,
    "collected_at": "2026-06-10T02:00:00Z",
    "note": "이 노선(ICN-NRT) 전체 출발일 통틀어 역대 최저가"
  }
}
```
> `data_gaps`: 원래 수집됐어야 할 날짜에 값이 없는 구간. 프론트에서 그래프를 그릴 때 이 구간은 실선 대신 점선/결측 표시로 구분해서, "가격이 매끄럽게 변한 것"처럼 보이지 않게 하기 위한 필드.

---

### 4. Best Month Itinerary API

#### `GET /v1/itineraries/best-in-month`
출발지/도착지와 월(month)만 주면, 그 달 안의 모든 (출발일, 귀국일) 조합을 Itinerary Search API와 동일한 기준(`sort_by`)으로 점수 매겨 순위별로 반환한다.

**Query**
| 이름 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `origin` | string | ✅ | |
| `destination` | string | ✅ | |
| `year_month` | string (YYYY-MM) | ✅ | 예: `2026-11` |
| `trip_length_days` | int | | 왕복 기준 체류 일수 (예: 3박 4일 → 3) |
| `sort_by` | cheapest\|best_schedule\|balanced | | 기본 balanced |
| `price_weight` | float (0~1) | | `balanced`일 때만 적용, 기본 0.6 |
| `currency` | KRW\|USD | | |
| `normalize_by` | none\|oil_price\|usd_krw | | |
| `limit`, `offset` | int | | |

**Response 예시**
```json
{
  "year_month": "2026-11",
  "sort_by": "balanced",
  "best_itineraries": [
    {
      "rank": 1,
      "score": 90.1,
      "depart_date": "2026-11-05",
      "return_date": "2026-11-08",
      "total_price": 298000,
      "total_price_normalized": 291500
    },
    {
      "rank": 2,
      "score": 87.6,
      "depart_date": "2026-11-19",
      "return_date": "2026-11-22",
      "total_price": 312000,
      "total_price_normalized": 305800
    }
  ]
}
```

---

### 5. Market Context API

#### `GET /v1/market-context`
날짜 또는 기간별 환율/유가 조회. 주로 2, 3, 4번의 `normalize_by` 계산에 내부적으로 쓰이지만, 그래프에 보조선을 그리기 위해 직접 조회할 수도 있다.

**Query**
| 이름 | 타입 | 설명 |
|---|---|---|
| `date` | string (YYYY-MM-DD) | 특정 하루 조회 |
| `date_from`, `date_to` | string (YYYY-MM-DD) | 기간 조회 (`date`와 배타적) |

**Response 예시**
```json
{
  "context": [
    {
      "context_date": "2026-11-01",
      "krw_usd_rate": 1358.0,
      "oil_price_usd": 80.1,
      "oil_price_30d_avg": 81.4
    }
  ]
}
```

---

### 6. Routes / System API (관리용, 인증 필요)

#### `GET /v1/admin/routes`
활성/중단 노선 전체 목록 (사용자용 4번과 달리 중단된 노선도 포함).

#### `POST /v1/admin/routes`
```json
{ "origin": "ICN", "destination": "NRT", "mode": "pair", "horizon_days": 365 }
```
`mode`: `pair`(양방향) | `one-way`(단방향)

#### `DELETE /v1/admin/routes/{origin}/{destination}`
해당 방향 추적 중단 (`deactivate`와 동일, 데이터는 보존).

#### `GET /v1/admin/system/status`
```json
{
  "active_tracked_dates": 2928,
  "stale_tracked_dates": 210,
  "stale_ratio": 0.072,
  "last_collection_success_at": "2026-07-06T09:14:00Z",
  "last_collection_error": null
}
```
지금 스케줄러 로그에 찍히는 `[!!] 경고` 판단 로직(`STALE_HOURS`, `STALE_WARN_RATIO`)을 그대로 API로 노출.

---

### 향후 확장 (지금 구현 범위 아님)

#### Price Alerts API
"이 노선이 N원 밑으로 떨어지면 알림" — 스키마/구현은 지금 만들지 않되, `/v1/alerts` 네임스페이스를 비워둔다.

---

### 참고: 몇 가지 설계에 대한 부가 설명
 
1. **왜 왕복 조합이 여러 개 나오나요?**
    편도 최저가 하나만 기계적으로 짝지어 보여주는 대신, 가격/일정 기준으로 점수를 매긴 여러 조합을 `sort_by` 값에 따라 나열합니다. 그래서 "가장 싼 조합"과 "가장 시간 활용이 좋은 조합"이 다르게 나올 수 있습니다.
 
2. **정규화 가격(`price_normalized`)은 어떻게 계산되나요?**
    "그때 가격을 지금 기준 유가/환율로 다시 환산하면 얼마였을지"를 계산한 값입니다.
    ```
    price_normalized_oil     = 그때_가격 × (오늘_유가 / 그때_유가)
    price_normalized_usd_krw = 그때_가격(KRW) / 오늘_환율
    ```
    예를 들어 유가가 그때 더 비쌌다면, 정규화된 가격은 실제 결제 가격보다 낮게 나옵니다 — "유가가 비싼 시기였는데도 이 가격이었으니, 지금 유가 기준으로는 더 싼 셈"이라는 뜻입니다.
 
3. **`data_gaps`는 왜 있나요?**
    서버 점검이나 일시적 장애로 특정 날짜의 가격을 못 가져온 구간을 표시합니다. 이 구간을 그래프에서 실선으로 이어버리면 "가격이 매끄럽게 변한 것"처럼 오해할 수 있어서, 점선이나 별도 표시로 구분할 수 있도록 제공합니다.
 
4. **`price_score`/`schedule_score`는 어떻게 계산되나요?**
    - `price_score`: 검색 결과 안에서 최저가를 100점, 최고가를 0점으로 상대 환산한 값
    - `schedule_score`: 출발시간, 귀국 도착시간, 경유 횟수, 소요시간 4가지를 각각 25%씩 반영한 평균값
    - `balanced` 정렬은 `price_score × price_weight + schedule_score × (1 - price_weight)`로 계산되며, `price_weight`(기본 0.6)는 쿼리 파라미터로 직접 조정할 수 있습니다.

5. **정규화 값에 `"experimental": true`가 붙어 있는 이유는요?**
    정규화 공식이 실제 가격 흐름을 얼마나 잘 설명하는지는 유가가 오르내리는 구간을 충분히 포함한 데이터(최소 90일 이상)로 검증이 필요합니다. 아직 이 검증이 끝나지 않아 참고용으로만 활용해달라는 의미로 표시하고 있으며, 검증이 끝나면 이 플래그는 제거될 예정입니다.