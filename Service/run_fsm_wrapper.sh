#!/bin/bash
# 이 스크립트는 systemd에 의해 실행됩니다.

set -e  # 오류 발생 시 즉시 종료하여 systemd 재시작 유도

log() {
  echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1"
}

# --- 설정 ---------------------------------------------------
FSM_APP_DIR="/home/user/dev/Release/MediDeployment"
FSM_FILE="run_fsm.py"
FSM_DEFAULT_VENV_PYTHON="${FSM_APP_DIR}/.venv/bin/python"
# ------------------------------------------------------------

cd "${FSM_APP_DIR}"

if [ -n "${FSM_PYTHON_BIN}" ]; then
  PYTHON_BIN="${FSM_PYTHON_BIN}"
elif [ -x "${FSM_DEFAULT_VENV_PYTHON}" ]; then
  PYTHON_BIN="${FSM_DEFAULT_VENV_PYTHON}"
else
  PYTHON_BIN="$(command -v python3)"
fi

if [ -z "${PYTHON_BIN}" ] || [ ! -x "${PYTHON_BIN}" ]; then
  log "Error: python executable not found. FSM_PYTHON_BIN=${FSM_PYTHON_BIN}"
  exit 1
fi

is_target_running() {
    # python 실행 경로가 달라도 run_fsm.py 프로세스를 정확히 찾도록 파일명 기준으로 확인
    if pgrep -f ".*/${FSM_FILE}" > /dev/null 2>&1; then
        return 0
    fi
    return 1
}

if is_target_running; then
    log "Warning: ${FSM_FILE} is already running. Exiting."
    exit 0
fi

log "Starting ${FSM_FILE} with ${PYTHON_BIN}..."
log "Python version: $(${PYTHON_BIN} --version 2>&1)"
exec "${PYTHON_BIN}" "${FSM_FILE}"
