# Flight Price Tracker

Google Flights의 항공권 가격을 주기적으로 수집해 MySQL에 저장하고, 그 데이터를 API로 제공하는 개인 프로젝트입니다.

## 구성 서비스

이 저장소는 서로 독립적인 두 서비스 + 공유 DB 계층으로 구성됩니다.

| 서비스 | 역할 | 문서 |
|---|---|---|
| `services/scheduler/` | Playwright로 Google Flights를 긁어와 가격을 수집하는 상시 프로세스 | [services/scheduler/README.md](services/scheduler/README.md) |
| `services/api/` | 수집된 데이터를 조회/추천하는 FastAPI 서버 | [services/api/README.md](services/api/README.md) |
| `shared/` | 두 서비스가 공통으로 쓰는 DB 접근 계층 (`db.py`, `market_context.py`) | 별도 문서 없음 (서비스 문서에서 참조) |

## 폴더 구조

```
flight-tracker/
├── shared/                 # DB 접근 계층 (두 서비스 공용)
├── services/
│   ├── scheduler/          # 가격 수집 서비스 — 문서: services/scheduler/README.md
│   └── api/                # 조회/추천 API 서비스 — 문서: services/api/README.md
├── docker/
│   ├── scheduler.dockerfile
│   └── api.dockerfile
└── docker-compose.yml
```

## 빠른 시작

```bash
git clone https://github.com/tsungmnli/flight-tracker.git
cd flight-tracker
nano .env   # 값 채우기
```

`.env` 파일을 열어 아래처럼 실제 값을 채워넣습니다.

```
FLIGHTS_DB_NAME=flights
FLIGHTS_DB_USER=<원하는 사용자명>
FLIGHTS_DB_PASSWORD=<원하는 비밀번호>
MYSQL_ROOT_PASSWORD=<원하는 root 비밀번호>
EIA_API_KEY=<https://www.eia.gov/opendata/register.php 에서 무료 발급>
```

`.env`는 `.gitignore`에 포함되어 있어 git에 올라가지 않습니다. 절대 커밋하지 마세요.

```bash
docker compose up -d --build
```

전체 서비스(`mysql`, `scheduler`, `api`)가 한 번에 뜹니다. 각 서비스별 세부 사용법(노선 추가, API 엔드포인트 등)은 위 표의 링크를 참고하세요.

## 상태 확인

```bash
docker compose ps
docker compose logs -f scheduler
docker compose logs -f api
```

## 자주 쓰는 명령어

| 목적 | 명령어 |
|---|---|
| 전체 켜기 | `docker compose up -d` |
| 전체 끄기 (데이터 유지) | `docker compose down` |
| 코드 수정 후 재빌드 | `docker compose up -d --build` |
| 컨테이너 상태 확인 (중지된 것 포함) | `docker compose ps -a` |
| DB만 완전 초기화 (주의) | `docker compose down && docker volume rm flight-tracker_mysql_data && docker compose up -d` |
| 컨테이너 + 모든 볼륨 삭제 (주의) | `docker compose down -v` |

서비스별 세부 명령어(노선 추가, API 호출 예시 등)는 각 서비스 문서를 참고하세요.