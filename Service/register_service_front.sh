#!/bin/bash
set -e

SERVICE_NAME="front.service"
WRAPPER_SCRIPT_NAME="run_front_wrapper.sh"

SCRIPT_SOURCE_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
APP_DIR="$( cd "${SCRIPT_SOURCE_DIR}/.." &> /dev/null && pwd )"
SYSTEMD_DIR="/etc/systemd/system"
WRAPPER_SCRIPT_PATH="${SCRIPT_SOURCE_DIR}/${WRAPPER_SCRIPT_NAME}"
SERVICE_FILE_PATH="${SYSTEMD_DIR}/${SERVICE_NAME}"

echo "================================================="
echo "Registering ${SERVICE_NAME}"
echo "================================================="

if [ "$(id -u)" -ne 0 ]; then
  echo "Error: This script must be run as root (e.g., sudo ./$(basename "$0"))"
  exit 1
fi

if [ ! -f "${WRAPPER_SCRIPT_PATH}" ]; then
    echo "Error: '${WRAPPER_SCRIPT_NAME}' not found in ${SCRIPT_SOURCE_DIR}"
    exit 1
fi

USER_NAME="$(logname 2>/dev/null || echo "$SUDO_USER")"
if [ -z "${USER_NAME}" ]; then
  echo "Error: Could not determine service user. Set SUDO_USER or run from a login session."
  exit 1
fi

echo "Setting executable permission for ${WRAPPER_SCRIPT_NAME}..."
chmod +x "${WRAPPER_SCRIPT_PATH}"

echo "Creating systemd service file at ${SERVICE_FILE_PATH}..."
cat > "${SERVICE_FILE_PATH}" <<EOF
[Unit]
Description=Front Service
After=network-online.target
Wants=network-online.target

[Service]
User=${USER_NAME}
WorkingDirectory=${APP_DIR}
ExecStart=${WRAPPER_SCRIPT_PATH}
Restart=always
RestartSec=5s
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

chmod 644 "${SERVICE_FILE_PATH}"

echo "Reloading systemd daemon..."
systemctl daemon-reload
echo "Enabling service to start on boot..."
systemctl enable "${SERVICE_NAME}"
echo "Starting/Restarting service..."
systemctl restart "${SERVICE_NAME}"

echo ""
echo "=========== Service Registration Complete ==========="
echo "User=${USER_NAME}"
echo "WorkingDirectory=${APP_DIR}"
