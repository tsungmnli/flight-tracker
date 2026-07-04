# Playwright 공식 이미지: 브라우저 바이너리 + 필요한 시스템 라이브러리(libnss3 등)가
# 이미 설치돼 있어서, requirements.txt의 playwright 버전과 태그만 맞춰주면 된다.
# 버전은 반드시 requirements.txt의 playwright==버전 과 동일해야 함.
FROM mcr.microsoft.com/playwright/python:v1.61.0-jammy

# WORKDIR을 고정해서 app.py의 상대경로(./playwright_profile)가
# 항상 /app/playwright_profile로 귀결되게 한다.
WORKDIR /app

# 의존성 레이어를 먼저 캐시하기 위해 requirements.txt만 먼저 복사
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 코드 복사
COPY app.py db.py manage_routes.py scheduler.py ./

# scheduler.py가 상시 실행되는 메인 프로세스
CMD ["python3", "scheduler.py"]