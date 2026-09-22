#!/usr/bin/env bash
# Evening day-close: export + reset today, arm RTC wake, optional poweroff.
# Usage:
#   sudo ./scripts/havikki-day-close.sh              # close + RTC + poweroff
#   sudo ./scripts/havikki-day-close.sh --dry-run    # close + RTC, no poweroff
#   sudo ./scripts/havikki-day-close.sh --no-poweroff
# Env /etc/havikkivaaka/power-schedule.conf:
#   POWER_OFF_TIME=18:00  POWER_ON_TIME=08:00  API_BASE=http://127.0.0.1:8080

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/scripts/havikki-power-lib.sh"
havikki_power_defaults

LOG="$LOG_DIR/havikki-day-close.log"
exec >>"$LOG" 2>&1

DRY=0
DO_POWEROFF=1
for arg in "$@"; do
  case "$arg" in
    --dry-run|--no-poweroff) DO_POWEROFF=0 ;;
    --poweroff) DO_POWEROFF=1 ;;
    -h|--help)
      echo "Usage: $0 [--dry-run|--no-poweroff]"
      exit 0
      ;;
  esac
done

havikki_log "==== day-close start (poweroff=$DO_POWEROFF) ===="

if ! havikki_api_wait 90; then
  havikki_log "ERROR: API not up at $API_BASE — abort (no poweroff)"
  exit 1
fi

TODAY="$(date +%F)"
if havikki_stamp_exists "$TODAY"; then
  havikki_log "stamp already exists for $TODAY — skip export/reset"
else
  havikki_close_day "$TODAY" true
fi

# Arm wake for next POWER_ON_TIME (needs root)
if [[ "$(id -u)" -eq 0 ]]; then
  havikki_rtc_arm_next "$POWER_ON_TIME" || true
else
  havikki_log "WARN: not root — skip RTC arm and poweroff"
  DO_POWEROFF=0
fi

havikki_log "REMINDER: turn OFF YKV + display mains switch after PC is down."

if [[ "$DO_POWEROFF" -eq 1 ]]; then
  havikki_log "poweroff in 5s…"
  sleep 5
  systemctl poweroff || /sbin/poweroff || shutdown -h now
else
  havikki_log "==== day-close done (no poweroff) ===="
fi
