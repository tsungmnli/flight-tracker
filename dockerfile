# Playwright 공식 이미지: 브라우저 바이너리 + 필요한 시스템 라이브러리(libnss3 등)가
# 이미 설치돼 있어서, requirements.txt의 playwright 버전과 태그만 맞춰주면 된다.
# 버전은 반드시 requirements.txt의 playwright==버전 과 동일해야 함.
FROM mcr.microsoft.com/playwright/python:v1.61.0-jammy

# WORKDIR을 고정해서 app.py의 상대경로(./playwright_profile)가
# 항상 /app/playwright_profile로 귀결되게 한다.
WORKDIR /app

# headless=False로 브라우저를 띄우려면 화면(디스플레이 서버)이 필요한데
# 컨테이너에는 모니터가 없으므로, 메모리 안에서만 동작하는 가짜 디스플레이(Xvfb)를 설치한다.
RUN apt-get update && apt-get install -y --no-install-recommends xvfb \
    && rm -rf /var/lib/apt/lists/*

# 의존성 레이어를 먼저 캐시하기 위해 requirements.txt만 먼저 복사
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 코드 복사
COPY app.py db.py manage_routes.py scheduler.py ./

# 시작 스크립트 복사 + 실행권한 부여
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# 컨테이너가 켜질 때마다 entrypoint.sh가 먼저 실행되어 잠금 파일을 정리한 뒤,
# 그 다음에 CMD(scheduler.py)를 실행한다.
# -u 옵션: 파이썬 출력 버퍼링을 끄고 print()를 즉시 로그로 내보낸다.
ENTRYPOINT ["/entrypoint.sh"]
CMD ["python3", "-u", "scheduler.py"]