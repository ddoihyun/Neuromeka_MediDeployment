#!/bin/bash
# 이 스크립트는 systemd에 의해 실행됩니다.

set -e  # 오류 발생 시 즉시 종료하여 systemd 재시작 유도

log() {
  echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1"
}

# --- 설정 ---------------------------------------------------
FSM_APP_DIR="/home/user/dev/Release/MediDeployment"
FSM_FILE="run_front.py"
# ------------------------------------------------------------

cd "${FSM_APP_DIR}"

is_target_running() {
    # set -e 환경에서 pgrep의 "미탐지(1)"는 정상 흐름이므로 if 조건에서 직접 처리
    if pgrep -f "python3 .*/${FSM_FILE}" > /dev/null 2>&1; then
        return 0
    fi
    return 1
}

if is_target_running; then
    log "Warning: ${FSM_FILE} is already running. Exiting."
    exit 0
fi

log "Starting ${FSM_FILE}..."
exec python3 "${FSM_FILE}"
