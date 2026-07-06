#!/bin/sh
# 전원 끊김/강제 종료 등 비정상 종료 이후 재시작할 때,
# Chromium이 남겨둔 잠금 파일(SingletonLock 등) 때문에
# "profile is in use by another process"로 계속 실패하는 문제를 막기 위한 스크립트.
#
# 스케줄러는 scraper.py를 한 번에 하나씩만 순차 실행하는 구조라서,
# 컨테이너 "시작 시점"에 이 잠금 파일이 남아있다면 그건 100% 이전 실행의 흔적이지
# 지금 실제로 누가 프로필을 쓰고 있는 상황일 수 없다. 그래서 무조건 지우고 시작해도 안전하다.

PROFILE_DIR="/app/playwright_profile"

if [ -d "$PROFILE_DIR" ]; then
  echo "[entrypoint] 이전 실행의 Chromium 잠금 파일 정리 중..."
  rm -f "$PROFILE_DIR/SingletonLock" \
        "$PROFILE_DIR/SingletonCookie" \
        "$PROFILE_DIR/SingletonSocket"
fi

# headless=False로 브라우저를 켜야 하는데 컨테이너엔 실제 화면이 없으므로,
# 가짜 디스플레이(Xvfb)를 백그라운드에서 켜고 그 화면 번호를 DISPLAY로 지정한다.
# 이렇게 하면 Chromium은 "화면이 있다"고 착각하고 정상적으로 headed 모드로 뜬다.
echo "[entrypoint] 가상 디스플레이(Xvfb) 시작 중..."
Xvfb :99 -screen 0 1920x1080x24 &
export DISPLAY=:99

# Xvfb가 완전히 준비될 시간을 잠깐 준다
sleep 1

exec "$@"