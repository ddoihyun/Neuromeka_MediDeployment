#!/bin/bash
set -e

# --- 설정 -----------------------
SERVICE_NAME="auto_chrome.service"
WRAPPER_SCRIPT_NAME="auto_chrome.sh"
SYSTEMD_DIR="/etc/systemd/system"
# --------------------------------

# 이 스크립트/auto_chrome.sh 가 있는 디렉토리
SCRIPT_SOURCE_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
WRAPPER_SCRIPT_PATH="${SCRIPT_SOURCE_DIR}/${WRAPPER_SCRIPT_NAME}"

echo "================================================="
echo "Registering ${SERVICE_NAME}"
echo "================================================="

# 0. Root 권한 확인
if [ "$(id -u)" -ne 0 ]; then
  echo "Error: This script must be run as root (e.g., sudo ./register_auto_chrome_service.sh)"
  exit 1
fi

# 1. 필요한 파일 존재 여부 확인
if [ ! -f "${WRAPPER_SCRIPT_PATH}" ]; then
    echo "Error: '${WRAPPER_SCRIPT_NAME}' not found in ${SCRIPT_SOURCE_DIR}"
    exit 1
fi

# 2. 실행 권한 부여
echo "Setting executable permission for ${WRAPPER_SCRIPT_NAME}..."
chmod +x "${WRAPPER_SCRIPT_PATH}"

# 3. 서비스 파일 생성 (현재 디렉토리 기준으로 자동 생성)
SERVICE_FILE_PATH="${SYSTEMD_DIR}/${SERVICE_NAME}"

# 로그인 사용자 이름 추정 (필요하면 'user'로 직접 바꿔도 됨)
USER_NAME="$(logname 2>/dev/null || echo "$SUDO_USER")"

if [ -z "${USER_NAME}" ]; then
  echo "Error: could not detect service user. Please set USER_NAME manually."
  exit 1
fi

echo "Creating systemd service file at ${SERVICE_FILE_PATH}..."
cat > "${SERVICE_FILE_PATH}" <<EOF2
[Unit]
Description=Auto start Chrome kiosk to http://127.0.0.1:3190
After=graphical.target front.service
Wants=graphical.target
Requires=front.service

[Service]
Type=simple
User=${USER_NAME}
Environment=DISPLAY=:0
Environment=AUTO_CHROME_URL=http://127.0.0.1:3190
Environment=AUTO_CHROME_WAIT_TIMEOUT=15
WorkingDirectory=${SCRIPT_SOURCE_DIR}
ExecStart=${WRAPPER_SCRIPT_PATH}
Restart=always
RestartSec=2

[Install]
WantedBy=graphical.target
EOF2

chmod 644 "${SERVICE_FILE_PATH}"

# 4. systemd 적용 및 서비스 시작
echo "Reloading systemd daemon..."
systemctl daemon-reload
echo "Enabling service to start on boot..."
systemctl enable "${SERVICE_NAME}"
echo "Starting/Restarting service..."
systemctl restart "${SERVICE_NAME}"

echo ""
echo "=========== Service Registration Complete ==========="
echo "부팅 후 자동으로 Chrome가 http://127.0.0.1:3190 로 실행됩니다."
