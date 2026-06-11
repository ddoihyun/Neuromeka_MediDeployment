#!/bin/bash
set -euo pipefail

URL="${AUTO_CHROME_URL:-http://127.0.0.1:3190}"
WAIT_TIMEOUT_SECONDS="${AUTO_CHROME_WAIT_TIMEOUT:-15}"
CHROME_BIN="/usr/bin/google-chrome"
CHROME_PROFILE_DIR="/tmp/auto-chrome-profile"

log() {
  echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*"
}

if [ ! -x "${CHROME_BIN}" ]; then
  log "Error: ${CHROME_BIN} not found or not executable"
  exit 1
fi

mkdir -p "${CHROME_PROFILE_DIR}"

log "Waiting for front service on ${URL} (timeout: ${WAIT_TIMEOUT_SECONDS}s) ..."
START_TIME="$(date +%s)"

while true; do
  if curl -fsS --max-time 1 "${URL}" >/dev/null 2>&1; then
    log "Front is up. Launching Chrome..."
    break
  fi

  NOW="$(date +%s)"
  if [ $((NOW - START_TIME)) -ge "${WAIT_TIMEOUT_SECONDS}" ]; then
    log "Front health check timeout reached. Launching Chrome anyway."
    break
  fi

  sleep 0.5
done

exec "${CHROME_BIN}" \
  --app="${URL}" \
  --kiosk \
  --noerrdialogs \
  --disable-infobars \
  --disable-session-crashed-bubble \
  --no-first-run \
  --no-default-browser-check \
  --disable-component-update \
  --disable-features=ChromeWhatsNewUI \
  --user-data-dir="${CHROME_PROFILE_DIR}" \
  --password-store=basic
