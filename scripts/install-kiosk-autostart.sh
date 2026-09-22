#!/usr/bin/env bash
# Idempotent install: YKV boot link + kiosk app systemd + LightDM autologin + Chromium autostart.
# Usage on Lenovo: sudo ./scripts/install-kiosk-autostart.sh
# Repo root must be /home/sami/havikkivaaka (or set HAVIKKI_ROOT).

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HAVIKKI_ROOT="${HAVIKKI_ROOT:-$ROOT}"
USER_NAME="${HAVIKKI_USER:-sami}"
USER_HOME="$(getent passwd "$USER_NAME" | cut -d: -f6)"
IFACE="${HAVIKKI_IFACE:-enp1s0}"
YKV_HOST="${HAVIKKI_HOST:-192.168.50.11}"
YKV_PORT="${HAVIKKI_PORT:-23}"
# 0.0.0.0 = admin UI reachable from another PC on the local switch (offline LAN)
HTTP_HOST="${HAVIKKI_HTTP_HOST:-0.0.0.0}"
HTTP_PORT="${HAVIKKI_HTTP_PORT:-8080}"
LOG_DIR="${HAVIKKI_LOG_DIR:-$HAVIKKI_ROOT/logs}"

die() { echo "ERROR: $*" >&2; exit 1; }

[[ "$(id -u)" -eq 0 ]] || die "run as root: sudo $0"
[[ -d "$HAVIKKI_ROOT" ]] || die "repo not found: $HAVIKKI_ROOT"
[[ -n "$USER_HOME" ]] || die "unknown user: $USER_NAME"
id "$USER_NAME" >/dev/null

mkdir -p "$LOG_DIR"
chown "$USER_NAME:$USER_NAME" "$LOG_DIR"
chmod 755 "$HAVIKKI_ROOT/scripts/"*.sh

# --- Stop conflicting manual mock / old kiosk servers (keep openssh) ---
echo "Stopping conflicting mock/kiosk processes (if any)..."
pkill -u "$USER_NAME" -f "python3 -m app.server" 2>/dev/null || true
pkill -u "$USER_NAME" -f "tools/kcp_mock.py" 2>/dev/null || true
# Do not kill all chromium — only our kiosk profile if present
pkill -u "$USER_NAME" -f "user-data-dir=/tmp/havikki-chrome-profile" 2>/dev/null || true
sleep 0.5

# --- Persist EEE off via NetworkManager when supported ---
if command -v nmcli >/dev/null 2>&1; then
  CONN="$(nmcli -g GENERAL.CONNECTION device show "$IFACE" 2>/dev/null || true)"
  if [[ -n "$CONN" && "$CONN" != "--" ]]; then
    if nmcli connection modify "$CONN" ethtool.eee-enabled no 2>/dev/null; then
      echo "NM: ethtool.eee-enabled=no on '$CONN'"
      nmcli connection up "$CONN" 2>/dev/null || true
    else
      echo "WARN: could not set ethtool.eee-enabled on '$CONN' (continuing; boot oneshot uses ethtool)"
    fi
  else
    echo "WARN: no NM connection on $IFACE — skip ethtool.eee-enabled"
  fi
fi

# --- systemd: YKV link oneshot ---
cat >/etc/systemd/system/havikki-ykv-link.service <<EOF
[Unit]
Description=Hävikkivaaka YKV Ethernet link (EEE off + dnsmasq DHCP)
After=network-online.target
Wants=network-online.target
# Keep SSH available; this unit only configures enp1s0 + dnsmasq

[Service]
Type=oneshot
RemainAfterExit=yes
Environment=HAVIKKI_LOG_DIR=$LOG_DIR
ExecStart=$HAVIKKI_ROOT/scripts/havikki-boot-ykv.sh $IFACE
ExecStop=$HAVIKKI_ROOT/scripts/disable-ykv-link.sh $IFACE
TimeoutStartSec=90

[Install]
WantedBy=multi-user.target
EOF

# --- systemd: kiosk app (live YKV) ---
cat >/etc/systemd/system/havikki-kiosk-app.service <<EOF
[Unit]
Description=Hävikkivaaka kiosk backend (live YKV KCP)
After=network-online.target havikki-ykv-link.service
Wants=network-online.target havikki-ykv-link.service
# Soft dependency: app still starts if YKV cable/DHCP is late (UI shows disconnected)

[Service]
Type=simple
User=$USER_NAME
Group=$USER_NAME
WorkingDirectory=$HAVIKKI_ROOT
Environment=PYTHONUNBUFFERED=1
Environment=HAVIKKI_LOG_DIR=$LOG_DIR
# Optional lab: HAVIKKI_MOCK=1 (start mock) or HAVIKKI_ALLOW_MOCK_FALLBACK=1 (live→mock after fail).
# Prefer clear "Ei yhteyttä YKV:hen" over silent mock when scale cable is absent.
ExecStartPre=+/bin/bash -c 'mkdir -p "$LOG_DIR"; chown $USER_NAME:$USER_NAME "$LOG_DIR"; touch "$LOG_DIR/kiosk-app.log"; chown $USER_NAME:$USER_NAME "$LOG_DIR/kiosk-app.log"'
ExecStart=/usr/bin/python3 -m app.server --host $YKV_HOST --port $YKV_PORT --http-host $HTTP_HOST --http-port $HTTP_PORT
Restart=always
RestartSec=3
StandardOutput=append:$LOG_DIR/kiosk-app.log
StandardError=append:$LOG_DIR/kiosk-app.log

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable havikki-ykv-link.service havikki-kiosk-app.service
systemctl restart havikki-ykv-link.service
systemctl restart havikki-kiosk-app.service

# --- LightDM autologin ---
mkdir -p /etc/lightdm/lightdm.conf.d
cat >/etc/lightdm/lightdm.conf.d/50-havikki-autologin.conf <<EOF
[Seat:*]
autologin-user=$USER_NAME
autologin-user-timeout=0
autologin-guest=false
EOF
echo "LightDM autologin → $USER_NAME (/etc/lightdm/lightdm.conf.d/50-havikki-autologin.conf)"

# --- Desktop autostart: Chromium only (app runs under systemd) ---
AUTOSTART_DIR="$USER_HOME/.config/autostart"
mkdir -p "$AUTOSTART_DIR"
cat >"$AUTOSTART_DIR/havikki-kiosk.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Hävikkivaaka Kiosk
Comment=Chromium kiosk after havikki-kiosk-app is up
Exec=$HAVIKKI_ROOT/scripts/start-kiosk.sh --live --browser-only
X-GNOME-Autostart-enabled=true
X-GNOME-Autostart-Delay=3
OnlyShowIn=XFCE;X-Cinnamon;GNOME;Unity;MATE;
EOF
chown -R "$USER_NAME:$USER_NAME" "$USER_HOME/.config"
echo "Autostart: $AUTOSTART_DIR/havikki-kiosk.desktop"

# Ensure openssh stays enabled
if systemctl list-unit-files ssh.service >/dev/null 2>&1; then
  systemctl enable --now ssh.service 2>/dev/null || true
elif systemctl list-unit-files sshd.service >/dev/null 2>&1; then
  systemctl enable --now sshd.service 2>/dev/null || true
fi

echo
echo "=== status ==="
systemctl --no-pager --full status havikki-ykv-link.service havikki-kiosk-app.service || true
echo
echo "Installed. Boot flow: network → havikki-ykv-link → havikki-kiosk-app → (login) Chromium kiosk."
echo "Stop kiosk UI:    pkill -f 'user-data-dir=/tmp/havikki-chrome-profile'  # or close Chromium"
echo "Stop app:         sudo systemctl stop havikki-kiosk-app"
echo "Disable boot:     sudo systemctl disable --now havikki-kiosk-app havikki-ykv-link"
echo "Disable autologin: sudo rm -f /etc/lightdm/lightdm.conf.d/50-havikki-autologin.conf"
echo "Remove autostart: rm -f $AUTOSTART_DIR/havikki-kiosk.desktop"
echo "Logs: $LOG_DIR/  and /tmp/havikki-*.log"
echo "Note: lab NOPASSWD sudo is OK for demo; do not use on untrusted networks."
