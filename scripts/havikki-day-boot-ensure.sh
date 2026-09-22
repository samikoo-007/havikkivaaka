#!/usr/bin/env bash
# Boot safety net: if yesterday was not day-closed, export + clear it now.
# Intended as systemd oneshot after havikki-kiosk-app is up.
# Usage: ./scripts/havikki-day-boot-ensure.sh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/scripts/havikki-power-lib.sh"
havikki_power_defaults

LOG="$LOG_DIR/havikki-day-boot-ensure.log"
exec >>"$LOG" 2>&1

havikki_log "==== boot-ensure start ===="

if ! havikki_api_wait 120; then
  havikki_log "ERROR: API not up — abort"
  exit 1
fi

TODAY="$(date +%F)"
if date -d "$TODAY -1 day" +%F >/dev/null 2>&1; then
  YDAY="$(date -d "$TODAY -1 day" +%F)"
else
  YDAY="$(date -v-1d +%F)"
fi

if havikki_stamp_exists "$YDAY"; then
  havikki_log "yesterday $YDAY already closed — nothing to do"
else
  # Only act if there are events for yesterday (avoid noise on fresh install)
  COUNT="$(curl -sf "$API_BASE/api/events?day=${YDAY}&limit=1" \
    | python3 -c 'import sys,json; d=json.load(sys.stdin); print(int((d.get("stats") or {}).get("count") or 0))' \
    2>/dev/null || echo 0)"
  if [[ "$COUNT" -gt 0 ]]; then
    havikki_log "yesterday $YDAY has $COUNT events and no stamp — closing now"
    havikki_close_day "$YDAY" true
  else
    havikki_log "yesterday $YDAY empty and no stamp — write stamp only"
    havikki_stamp_write "$YDAY" "empty-boot"
  fi
fi

# Re-arm RTC for next morning in case wakealarm was cleared after boot
if [[ "$(id -u)" -eq 0 ]]; then
  havikki_rtc_arm_next "$POWER_ON_TIME" || true
fi

havikki_log "REMINDER: ensure YKV + display mains switch is ON for the day."
havikki_log "==== boot-ensure done ===="
