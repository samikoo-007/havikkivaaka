#!/usr/bin/env bash
# Install daily power schedule: evening day-close (+RTC +poweroff) and boot ensure.
# Usage: sudo ./scripts/install-power-schedule.sh
# Optional env:
#   HAVIKKI_POWER_OFF_TIME=18:00
#   HAVIKKI_POWER_ON_TIME=08:00
#   HAVIKKI_ROOT=/home/sami/havikkivaaka
#
# Does NOT control YKV/display mains — use a wall switch / timed outlet.
# Enable BIOS RTC wake on the edge PC (see docs/power-schedule.md).

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HAVIKKI_ROOT="${HAVIKKI_ROOT:-$ROOT}"
USER_NAME="${HAVIKKI_USER:-sami}"
LOG_DIR="${HAVIKKI_LOG_DIR:-$HAVIKKI_ROOT/logs}"
POWER_OFF_TIME="${HAVIKKI_POWER_OFF_TIME:-18:00}"
POWER_ON_TIME="${HAVIKKI_POWER_ON_TIME:-08:00}"
API_BASE="${HAVIKKI_API_BASE:-http://127.0.0.1:8080}"

die() { echo "ERROR: $*" >&2; exit 1; }

[[ "$(id -u)" -eq 0 ]] || die "run as root: sudo $0"
[[ -d "$HAVIKKI_ROOT" ]] || die "repo not found: $HAVIKKI_ROOT"
[[ -x "$HAVIKKI_ROOT/scripts/havikki-day-close.sh" ]] || chmod +x "$HAVIKKI_ROOT/scripts/"*.sh

mkdir -p "$LOG_DIR" /etc/havikkivaaka
chown "$USER_NAME:$USER_NAME" "$LOG_DIR" 2>/dev/null || true

CONF=/etc/havikkivaaka/power-schedule.conf
if [[ ! -f "$CONF" ]]; then
  cat >"$CONF" <<EOF
# Hävikkivaaka daily power schedule (sourced by scripts)
POWER_OFF_TIME=$POWER_OFF_TIME
POWER_ON_TIME=$POWER_ON_TIME
API_BASE=$API_BASE
HAVIKKI_ROOT=$HAVIKKI_ROOT
HAVIKKI_LOG_DIR=$LOG_DIR
EOF
  echo "Wrote $CONF"
else
  echo "Keep existing $CONF (edit POWER_*_TIME there)"
fi

# --- evening close + poweroff ---
cat >/etc/systemd/system/havikki-day-close.service <<EOF
[Unit]
Description=Hävikkivaaka evening day-close (export+reset, RTC arm, poweroff)
After=havikki-kiosk-app.service
Wants=havikki-kiosk-app.service

[Service]
Type=oneshot
EnvironmentFile=-/etc/havikkivaaka/power-schedule.conf
Environment=HAVIKKI_ROOT=$HAVIKKI_ROOT
Environment=HAVIKKI_LOG_DIR=$LOG_DIR
ExecStart=$HAVIKKI_ROOT/scripts/havikki-day-close.sh
# Allow script to initiate poweroff
TimeoutStartSec=180
EOF

# OnCalendar uses local time; Persistent catches missed runs after long off periods
# (boot-ensure still handles missed close).
cat >/etc/systemd/system/havikki-day-close.timer <<EOF
[Unit]
Description=Hävikkivaaka evening day-close timer ($POWER_OFF_TIME)

[Timer]
OnCalendar=*-*-* $POWER_OFF_TIME:00
Persistent=true
Unit=havikki-day-close.service

[Install]
WantedBy=timers.target
EOF

# --- boot ensure ---
cat >/etc/systemd/system/havikki-day-boot-ensure.service <<EOF
[Unit]
Description=Hävikkivaaka boot day-close safety net (missed evening close)
After=havikki-kiosk-app.service
Wants=havikki-kiosk-app.service

[Service]
Type=oneshot
User=root
EnvironmentFile=-/etc/havikkivaaka/power-schedule.conf
Environment=HAVIKKI_ROOT=$HAVIKKI_ROOT
Environment=HAVIKKI_LOG_DIR=$LOG_DIR
ExecStart=$HAVIKKI_ROOT/scripts/havikki-day-boot-ensure.sh
TimeoutStartSec=180

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now havikki-day-close.timer
systemctl enable havikki-day-boot-ensure.service
# Run boot-ensure once now if app is already up (idempotent)
systemctl start havikki-day-boot-ensure.service 2>/dev/null || true

echo
echo "Installed power schedule:"
echo "  config:  $CONF"
echo "  timer:   havikki-day-close.timer  @ $POWER_OFF_TIME (export+reset+RTC+poweroff)"
echo "  boot:    havikki-day-boot-ensure.service (missed close)"
echo "  RTC tool: sudo $HAVIKKI_ROOT/scripts/havikki-rtc-wake.sh status|arm|clear"
echo
echo "BIOS: enable RTC / Resume by Alarm, then test:"
echo "  sudo $HAVIKKI_ROOT/scripts/havikki-rtc-wake.sh arm"
echo "  # or arm +3 min manually, then: sudo systemctl start havikki-day-close.service"
echo "  # with --no-poweroff first: sudo $HAVIKKI_ROOT/scripts/havikki-day-close.sh --dry-run"
echo
echo "YKV + displays: mains OFF via wall switch / timed outlet (not controlled by these units)."
systemctl --no-pager --full status havikki-day-close.timer || true
