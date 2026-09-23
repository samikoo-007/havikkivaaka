#!/usr/bin/env bash
# Shared helpers for Hävikkivaaka daily power / day-close scripts.
# shellcheck shell=bash

havikki_power_defaults() {
  ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  HAVIKKI_ROOT="${HAVIKKI_ROOT:-$ROOT}"
  LOG_DIR="${HAVIKKI_LOG_DIR:-$HAVIKKI_ROOT/logs}"
  STAMP_DIR="${HAVIKKI_DAY_CLOSE_STAMP_DIR:-$HAVIKKI_ROOT/data/day-close-stamps}"
  API_BASE="${HAVIKKI_API_BASE:-http://127.0.0.1:8080}"
  POWER_OFF_TIME="${HAVIKKI_POWER_OFF_TIME:-18:00}"
  POWER_ON_TIME="${HAVIKKI_POWER_ON_TIME:-08:00}"
  # Optional drop-in: /etc/havikkivaaka/power-schedule.conf
  if [[ -f /etc/havikkivaaka/power-schedule.conf ]]; then
    # shellcheck disable=SC1091
    source /etc/havikkivaaka/power-schedule.conf
  fi
  # Admin PIN for mutating API (same file as systemd EnvironmentFile)
  if [[ -f /etc/havikkivaaka/env ]]; then
    # shellcheck disable=SC1091
    set -a
    # shellcheck disable=SC1091
    source /etc/havikkivaaka/env
    set +a
  fi
  mkdir -p "$LOG_DIR" "$STAMP_DIR"
}

havikki_log() {
  echo "$(date -Is) $*"
}

havikki_api_wait() {
  local max="${1:-60}"
  local i
  for i in $(seq 1 "$max"); do
    if curl -sf "$API_BASE/api/health" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  return 1
}

havikki_api_json() {
  # usage: havikki_api_json POST /api/export/day '{"day":"..."}'
  local method="$1"
  local path="$2"
  local body="${3:-{}}"
  local -a hdr=(-H "Content-Type: application/json")
  if [[ -n "${HAVIKKI_ADMIN_PIN:-}" ]]; then
    hdr+=(-H "X-Havikki-Pin: ${HAVIKKI_ADMIN_PIN}")
  fi
  curl -sf -X "$method" "$API_BASE$path" \
    "${hdr[@]}" \
    -d "$body"
}

havikki_stamp_path() {
  local day="$1"
  echo "$STAMP_DIR/${day}.ok"
}

havikki_stamp_write() {
  local day="$1"
  local note="${2:-ok}"
  printf '%s %s\n' "$(date -Is)" "$note" >"$(havikki_stamp_path "$day")"
}

havikki_stamp_exists() {
  local day="$1"
  [[ -f "$(havikki_stamp_path "$day")" ]]
}

# Export + clear one calendar day via API. Does not power off.
havikki_close_day() {
  local day="$1"
  local export_first="${2:-true}"
  havikki_log "close_day day=$day export_first=$export_first"
  local body
  body="$(printf '{"day":"%s","export_first":%s}' "$day" "$export_first")"
  local resp
  resp="$(havikki_api_json POST /api/reset-day "$body")" || {
    havikki_log "ERROR: reset-day failed for $day"
    return 1
  }
  havikki_log "close_day resp=$resp"
  havikki_stamp_write "$day" "closed"
}

# Set RTC wakealarm for next POWER_ON_TIME (local). Requires root + BIOS RTC wake enabled.
havikki_rtc_arm_next() {
  local on_hm="$1"
  local rtc="${HAVIKKI_RTC:-/sys/class/rtc/rtc0/wakealarm}"
  if [[ ! -w "$rtc" ]]; then
    havikki_log "WARN: RTC wakealarm not writable ($rtc) — skip arm (check BIOS + permissions)"
    return 0
  fi
  local today tomorrow target epoch
  today="$(date +%F)"
  tomorrow="$(date -d "$today +1 day" +%F 2>/dev/null || date -v+1d +%F)"
  # If we arm after midnight before morning wake, target today; else tomorrow.
  local now_hm
  now_hm="$(date +%H:%M)"
  if [[ "$now_hm" < "$on_hm" ]]; then
    target="$today"
  else
    target="$tomorrow"
  fi
  if date -d "${target} ${on_hm}:00" +%s >/dev/null 2>&1; then
    epoch="$(date -d "${target} ${on_hm}:00" +%s)"
  else
    # macOS BSD date fallback (lab only)
    epoch="$(date -j -f "%Y-%m-%d %H:%M:%S" "${target} ${on_hm}:00" +%s)"
  fi
  echo 0 >"$rtc" 2>/dev/null || true
  echo "$epoch" >"$rtc"
  havikki_log "RTC wake armed → ${target} ${on_hm} (epoch=$epoch) via $rtc"
}
