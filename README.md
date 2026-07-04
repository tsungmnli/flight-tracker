# Flight Price Tracker

Google Flights의 항공권 가격을 주기적으로 수집해 MySQL에 저장하는 홈서버용 스케줄러입니다.
Playwright로 브라우저를 직접 제어해 데이터를 가져오며, 전체 구성은 Docker Compose로 관리됩니다.

## 구성

| 파일                 | 역할                                                                               |
| -------------------- | ---------------------------------------------------------------------------------- |
| `app.py`             | 노선 하나(출발지, 도착지, 날짜)의 항공권 데이터를 실제로 긁어오는 스크립트         |
| `scheduler.py`       | `routes`/`tracked_dates` 테이블을 보고 `app.py`를 계속 반복 실행하는 상시 프로세스 |
| `manage_routes.py`   | 추적할 노선을 추가/조회/중단하는 CLI 도구                                          |
| `market_context.py`  | 하루 1회 KRW-USD 환율과 WTI 유가(+30일 평균)를 받아와 저장                         |
| `db.py`              | MySQL 연결 및 테이블 초기화 로직                                                   |
| `Dockerfile`         | Playwright + Xvfb(가상 디스플레이)가 포함된 실행 이미지 정의                       |
| `entrypoint.sh`      | 컨테이너 시작 시 이전 실행의 잠금 파일 정리 + 가상 디스플레이 실행                 |
| `docker-compose.yml` | MySQL + 스케줄러 컨테이너를 함께 띄우는 설정                                       |

## 사전 준비

- Docker / Docker Compose 설치되어 있을 것
- 이 저장소를 홈서버에 clone

```bash
git clone https://github.com/tsungmnli/flight-tracker.git
cd flight-tracker
```

## 1. 환경변수 설정

```bash
nano .env
```

`.env` 파일을 열어 아래처럼 실제 값을 채워넣습니다.

```
FLIGHTS_DB_NAME=flights
FLIGHTS_DB_USER=<원하는 사용자명>
FLIGHTS_DB_PASSWORD=<원하는 비밀번호>
MYSQL_ROOT_PASSWORD=<원하는 root 비밀번호>
EIA_API_KEY=<https://www.eia.gov/opendata/register.php 에서 무료 발급>
```

`EIA_API_KEY`는 유가(WTI) 조회에만 쓰입니다. 비워두면 유가 조회는 건너뛰고 환율만 저장됩니다.

## 2. 빌드 및 실행

```bash
docker compose up -d --build
```

상태 확인:

```bash
docker compose ps
```

`mysql`이 `healthy`, `scheduler`가 `Up` 상태면 정상입니다.

로그 확인:

```bash
docker compose logs -f scheduler
```

## 추적 노선 추가하기

노선은 컨테이너 안에서 `manage_routes.py`로 관리합니다.

```bash
docker compose exec scheduler python manage_routes.py add ICN NRT                     # 양방향 추가 (기본 365일)
docker compose exec scheduler python manage_routes.py add-one ICN NRT                 # 한쪽 방향만 추가
docker compose exec scheduler python manage_routes.py add ICN NRT --horizon-days 180  # 추적 범위 지정
docker compose exec scheduler python manage_routes.py list                            # 등록된 노선 확인
docker compose exec scheduler python manage_routes.py deactivate ICN NRT              # 한쪽 방향 추적 중단 (데이터는 보존)
```

노선을 추가/변경하면 스케줄러가 **최대 1시간 이내**에 자동으로 반영합니다. 바로 반영하고 싶다면:

```bash
docker compose restart scheduler
```

## 자주 쓰는 명령어

**컨테이너 켜고 끄기**

| 목적                    | 명령어                             |
| ----------------------- | ---------------------------------- |
| 전체 켜기               | `docker compose up -d`             |
| 전체 끄기 (데이터 유지) | `docker compose down`              |
| 잠깐 멈추기             | `docker compose stop`              |
| 멈춘 컨테이너 재개      | `docker compose start`             |
| 코드 수정 후 재빌드     | `docker compose up -d --build`     |
| 스케줄러만 재시작       | `docker compose restart scheduler` |

**상태 및 로그 확인**

| 목적                                | 명령어                             |
| ----------------------------------- | ---------------------------------- |
| 실시간 로그 보기                    | `docker compose logs -f scheduler` |
| 지금까지 쌓인 로그 전체 보기        | `docker compose logs scheduler`    |
| 컨테이너 상태 확인 (중지된 것 포함) | `docker compose ps -a`             |

**노선 관리**

| 목적                    | 명령어                                                                 |
| ----------------------- | ---------------------------------------------------------------------- |
| 노선 추가 (양방향)      | `docker compose exec scheduler python manage_routes.py add A B`        |
| 노선 추가 (한쪽 방향만) | `docker compose exec scheduler python manage_routes.py add-one A B`    |
| 노선 목록               | `docker compose exec scheduler python manage_routes.py list`           |
| 노선 중단               | `docker compose exec scheduler python manage_routes.py deactivate A B` |

**초기화 (주의)**

| 목적                      | 명령어                                                                                      |
| ------------------------- | ------------------------------------------------------------------------------------------- |
| DB만 완전 초기화          | `docker compose down && docker volume rm flight-tracker_mysql_data && docker compose up -d` |
| 컨테이너 + 모든 볼륨 삭제 | `docker compose down -v`                                                                    |
