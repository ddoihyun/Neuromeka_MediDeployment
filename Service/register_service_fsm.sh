#!/bin/bash
set -e

# --- 설정 -----------------------
SERVICE_NAME="fsm.service"
WRAPPER_SCRIPT_NAME="run_fsm_wrapper.sh"
SYSTEMD_DIR="/etc/systemd/system"
# -------------------------------


# 스크립트 파일들이 위치한 현재 디렉토리
SCRIPT_SOURCE_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
WRAPPER_SCRIPT_PATH="${SCRIPT_SOURCE_DIR}/${WRAPPER_SCRIPT_NAME}"

# MediDeployment 루트 경로 추정 (Service 디렉토리의 상위)
APP_DIR="$(cd "${SCRIPT_SOURCE_DIR}/.." && pwd)"

# 로그인 사용자 이름 추정 (sudo 환경 포함)
USER_NAME="$(logname 2>/dev/null || echo "${SUDO_USER}")"

if [ -z "${USER_NAME}" ]; then
  echo "Error: Could not resolve service user (logname/SUDO_USER)."
  exit 1
fi

echo "================================================="
echo "Registering ${SERVICE_NAME}"
echo "================================================="

# 0. Root 권한 확인
if [ "$(id -u)" -ne 0 ]; then
  echo "Error: This script must be run as root (e.g., sudo ./register_service.sh)"
  exit 1
fi

# 1. 필요한 파일 존재 여부 확인
if [ ! -f "${WRAPPER_SCRIPT_PATH}" ]; then
    echo "Error: '${WRAPPER_SCRIPT_NAME}' not found in ${SCRIPT_SOURCE_DIR}."
    exit 1
fi

# 2. 래퍼 스크립트에 실행 권한 부여
echo "Setting executable permission for ${WRAPPER_SCRIPT_NAME}..."
chmod +x "${WRAPPER_SCRIPT_PATH}"

# 3. 서비스 파일 생성 (현재 경로/사용자 자동 반영)
SERVICE_FILE_PATH="${SYSTEMD_DIR}/${SERVICE_NAME}"
echo "Creating systemd service file at ${SERVICE_FILE_PATH}..."
cat > "${SERVICE_FILE_PATH}" <<EOF
[Unit]
Description=FSM Service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${USER_NAME}
WorkingDirectory=${APP_DIR}
# Optional override file (example): FSM_PYTHON_BIN=/home/user/dev/Release/MediDeployment/.venv/bin/python
EnvironmentFile=-/etc/default/fsm
ExecStart=/bin/bash ${WRAPPER_SCRIPT_PATH}

Restart=always
RestartSec=5s

StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
chmod 644 "${SERVICE_FILE_PATH}"

# 4. Systemd 설정 적용 및 서비스 시작
echo "Reloading systemd daemon..."
systemctl daemon-reload
echo "Enabling service to start on boot..."
systemctl enable "${SERVICE_NAME}"
echo "Starting/Restarting service..."
systemctl restart "${SERVICE_NAME}"

echo ""
echo "=========== Service Registration Complete ==========="
