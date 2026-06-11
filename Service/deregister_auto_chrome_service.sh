#!/bin/bash
set -e

# --- 설정 -----------------------
SERVICE_NAME="auto_chrome.service"
SYSTEMD_DIR="/etc/systemd/system"
# -------------------------------

echo "================================================="
echo "Deregistering ${SERVICE_NAME}"
echo "================================================="

if [ "$(id -u)" -ne 0 ]; then
  echo "Error: This script must be run as root (e.g., sudo ./deregister_auto_chrome_service.sh)"
  exit 1
fi

# 1. 서비스 중지 및 비활성화
echo "Stopping the service..."
systemctl stop "${SERVICE_NAME}" || true
echo "Disabling the service..."
systemctl disable "${SERVICE_NAME}" || true

# 2. Systemd 서비스 파일 삭제
echo "Removing systemd service file..."
rm -f "${SYSTEMD_DIR}/${SERVICE_NAME}"

# 3. Systemd 설정 리로드
echo "Reloading systemd daemon..."
systemctl daemon-reload

echo ""
echo "=========== Service Deregistration Complete ==========="
echo "Note: auto_chrome.sh 파일은 그대로 남아 있습니다."
