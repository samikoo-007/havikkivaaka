#!/usr/bin/env bash
# Start kiosk backend + Chromium fullscreen, or Chromium only when systemd runs the app.
# Usage:
#   ./scripts/start-kiosk.sh                    # mock (default, dry-run) + chrome
#   ./scripts/start-kiosk.sh --live             # real YKV at 192.168.50.11:23 + chrome
#   ./scripts/start-kiosk.sh --live --browser-only   # wait for existing app, chrome only
#   SETTLE=2 ./scripts/start-kiosk.sh           # faster smile/frown for demo

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p "$ROOT/logs"

MODE="mock"
SETTLE="${SETTLE:-2}"
HTTP_PORT="${HTTP_PORT:-8080}"
BROWSER_ONLY=0
WAIT_SECS="${HAVIKKI_WAIT_SECS:-120}"

for arg in "$@"; do
  case "$arg" in
    --live) MODE="live"; SETTLE="${SETTLE_LIVE:-10}" ;;
    --browser-only) BROWSER_ONLY=1 ;;
    --help|-h)
      sed -n '2,8p' "$0"
      exit 0
      ;;
  esac
done

wait_for_api() {
  local i
  echo "Waiting for http://127.0.0.1:${HTTP_PORT}/api/state (up to ${WAIT_SECS}s)..."
  for i in $(seq 1 "$WAIT_SECS"); do
    if curl -sf "http://127.0.0.1:${HTTP_PORT}/api/state" >/dev/null; then
      echo "API ready"
      return 0
    fi
    sleep 1
  done
  echo "ERROR: API not ready after ${WAIT_SECS}s" >&2
  return 1
}

launch_chrome() {
  local CHROME
  CHROME="$(command -v chromium-browser || command -v chromium || true)"
  if [[ -z "$CHROME" ]]; then
    echo "Chromium not found — open http://127.0.0.1:${HTTP_PORT}/ manually"
    return 1
  fi
  # Prefer dedicated profile so we can stop kiosk without killing other Chrome windows
  mkdir -p /tmp/havikki-chrome-profile
  DISPLAY="${DISPLAY:-:0}" "$CHROME" --kiosk --app="http://127.0.0.1:${HTTP_PORT}/" \
    --no-first-run --disable-features=TranslateUI \
    --user-data-dir=/tmp/havikki-chrome-profile \
    --check-for-update-interval=31536000 \
    >/tmp/havikki-chrome.log 2>&1 &
  echo "chromium pid $! (DISPLAY=${DISPLAY:-:0})"
}

if [[ "$BROWSER_ONLY" -eq 1 ]]; then
  wait_for_api
  # Avoid a second Chromium kiosk if one is already up
  if pgrep -f "user-data-dir=/tmp/havikki-chrome-profile" >/dev/null 2>&1; then
    echo "kiosk Chromium already running — skip launch"
    exit 0
  fi
  launch_chrome
  echo "kiosk browser started (server managed externally, mode hint=$MODE)"
  exit 0
fi

pkill -f "python3 -m app.server" 2>/dev/null || true
sleep 0.3

HTTP_HOST="${HAVIKKI_HTTP_HOST:-0.0.0.0}"
if [[ "$MODE" == "mock" ]]; then
  python3 -m app.server --mock --http-host "$HTTP_HOST" --http-port "$HTTP_PORT" --settle-s "$SETTLE" \
    >>"$ROOT/logs/kiosk-app-manual.log" 2>&1 &
else
  python3 -m app.server --host "${HAVIKKI_HOST:-192.168.50.11}" --port "${HAVIKKI_PORT:-23}" \
    --http-host "$HTTP_HOST" --http-port "$HTTP_PORT" --settle-s "$SETTLE" \
    >>"$ROOT/logs/kiosk-app-manual.log" 2>&1 &
fi
SERVER_PID=$!
echo "server pid $SERVER_PID"

wait_for_api || { kill "$SERVER_PID" 2>/dev/null || true; exit 1; }
launch_chrome || wait "$SERVER_PID"
echo "kiosk started ($MODE). Stop: pkill -f 'python3 -m app.server'; pkill -f 'user-data-dir=/tmp/havikki-chrome-profile'"
