#!/usr/bin/env bash
# Arm / show / clear Linux RTC wakealarm (production helper).
# Usage:
#   sudo ./scripts/havikki-rtc-wake.sh status
#   sudo ./scripts/havikki-rtc-wake.sh arm [HH:MM]     # default POWER_ON_TIME / 08:00
#   sudo ./scripts/havikki-rtc-wake.sh clear
#
# BIOS: enable "Resume by RTC Alarm" / "Wake on Alarm" (wording varies).
# Test: arm for +3 minutes, poweroff, confirm machine wakes.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/scripts/havikki-power-lib.sh"
havikki_power_defaults

RTC="${HAVIKKI_RTC:-/sys/class/rtc/rtc0/wakealarm}"
CMD="${1:-status}"
WHEN="${2:-$POWER_ON_TIME}"

die() { echo "ERROR: $*" >&2; exit 1; }

case "$CMD" in
  status)
    echo "RTC device: ${HAVIKKI_RTC_DEV:-/sys/class/rtc/rtc0}"
    if [[ -f /sys/class/rtc/rtc0/wakealarm ]]; then
      echo "wakealarm: $(cat /sys/class/rtc/rtc0/wakealarm 2>/dev/null || echo '?')"
    else
      echo "wakealarm: (no rtc0/wakealarm — kernel/BIOS may lack RTC wake)"
    fi
    if command -v timedatectl >/dev/null 2>&1; then
      timedatectl | head -8
    fi
    echo "Configured POWER_ON_TIME=$POWER_ON_TIME POWER_OFF_TIME=$POWER_OFF_TIME"
    echo "BIOS checklist: enable RTC/alarm wake; disable deep G3 if wake fails."
    ;;
  arm)
    [[ "$(id -u)" -eq 0 ]] || die "run as root"
    [[ -w "$RTC" ]] || die "cannot write $RTC"
    havikki_rtc_arm_next "$WHEN"
    echo "Armed for $WHEN (see $RTC)"
    ;;
  clear)
    [[ "$(id -u)" -eq 0 ]] || die "run as root"
    [[ -w "$RTC" ]] || die "cannot write $RTC"
    echo 0 >"$RTC"
    echo "Cleared $RTC"
    ;;
  *)
    echo "Usage: $0 status|arm [HH:MM]|clear"
    exit 1
    ;;
esac
