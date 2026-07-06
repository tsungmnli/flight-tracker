# Scheduler Service

Google Flights의 항공권 가격을 주기적으로 수집해 MySQL에 저장하는 상시 프로세스입니다.
Playwright로 브라우저를 직접 제어하며, 노선(routes)과 추적 대상 날짜(tracked_dates)는 DB 테이블 기준으로 동작합니다.

전체 프로젝트 개요는 [README](../../README.md) 참고.

## 구성 파일

| 파일 | 역할 |
|---|---|
| `scraper.py` | 노선 하나(출발지, 도착지, 날짜)의 항공권 데이터를 실제로 긁어오는 스크립트 (구 `app.py`) |
| `scheduler.py` | `routes`/`tracked_dates` 테이블을 보고 `scraper.py`를 계속 반복 실행하는 상시 프로세스 |
| `manage_routes.py` | 추적할 노선을 추가/조회/중단하는 CLI 도구 |

DB 접근 로직(`db.py`, `market_context.py`)은 `shared/`에 있으며 API 서비스와 공유합니다.

`manage-routes`는 `python -m services.scheduler.manage_routes`를 짧게 실행하기 위해 이미지에 심어둔 래퍼 스크립트입니다 (`docker/manage-routes`, `scheduler.Dockerfile`에서 `/usr/local/bin/manage-routes`로 설치됨).

## 추적 노선 추가하기

```bash
# 양방향 추가 (기본 365일)
docker compose exec scheduler manage-routes add ICN NRT

# 한쪽 방향만 추가
docker compose exec scheduler manage-routes add-one ICN NRT

# 추적 범위 지정
docker compose exec scheduler manage-routes add ICN NRT --horizon-days 180

# 등록된 노선 확인
docker compose exec scheduler manage-routes list

# 한쪽 방향 추적 중단 (데이터는 보존)
docker compose exec scheduler manage-routes deactivate ICN NRT
```

노선을 추가/변경하면 스케줄러가 **최대 1시간 이내**에 자동으로 반영합니다. 바로 반영하고 싶다면:
```bash
docker compose restart scheduler
```

## 자주 쓰는 명령어

| 목적 | 명령어 |
|---|---|
| 실시간 로그 보기 | `docker compose logs -f scheduler` |
| 지금까지 쌓인 로그 전체 보기 | `docker compose logs scheduler` |
| 스케줄러만 재시작 | `docker compose restart scheduler` |
| 노선 목록 | `docker compose exec scheduler manage-routes list` |

## 트러블슈팅

**로그가 아무것도 안 뜬다**
`docker compose logs scheduler` (`-f` 없이)로 지금까지 쌓인 로그를 먼저 확인하세요.

**`profile appears to be in use by another Chromium process`**
전원 끊김 등 비정상 종료 후 Chromium 잠금 파일이 남아서 생기는 문제입니다. `entrypoint.sh`가 컨테이너 시작 시 자동으로 정리합니다.

**`Missing X server or $DISPLAY`**
`scraper.py`가 `headless=False`로 브라우저를 띄우는데 컨테이너엔 화면이 없어서 나는 에러입니다. `entrypoint.sh`에서 Xvfb(가상 디스플레이)를 띄워 해결했습니다.

**"활성 대상의 N%가 30시간 넘게 갱신되지 못했습니다" 경고**
등록된 노선·날짜 조합을 하루 안에 다 처리하지 못하고 있다는 경고입니다. 최근 장애 복구 직후라면 밀린 물량을 처리하는 중일 수 있으니 몇 시간 지켜보세요. 하루가 지나도 비율이 안 줄어들면 노선 수를 줄이거나 `--horizon-days`를 낮추는 것을 고려하세요.

**`ModuleNotFoundError: No module named 'shared'`**
스크립트를 `python3 services/scheduler/scheduler.py`처럼 경로로 직접 실행하면 발생합니다. 반드시 `python3 -m services.scheduler.scheduler`처럼 **모듈로 실행**하거나, `PYTHONPATH=/app`이 설정되어 있는지 확인하세요 (Dockerfile에 이미 반영되어 있어야 합니다).