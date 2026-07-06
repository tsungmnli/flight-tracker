FROM mcr.microsoft.com/playwright/python:v1.61.0-jammy

WORKDIR /app

ENV PYTHONPATH=/app

# headless=False로 브라우저를 띄우려면 화면(디스플레이 서버)이 필요한데
# 컨테이너에는 모니터가 없으므로, 메모리 안에서만 동작하는 가짜 디스플레이(Xvfb)를 설치한다.
RUN apt-get update && apt-get install -y --no-install-recommends xvfb \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared/ ./shared/
COPY services/scheduler/ ./services/scheduler/

# 시작 스크립트 복사 + 실행권한 부여
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["python3", "-u", "services/scheduler/scheduler.py"]