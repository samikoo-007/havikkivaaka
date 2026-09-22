#!/usr/bin/env bash
# Wrapper: optional Ethernet/DHCP setup, wait for YKV, then read-only KCP listen.
# Does not send T/Z. Does not start unless you run this script.
#
# Usage:
#   ./scripts/listen-ykv.sh [--setup] [--once] [--duration N] [--mode auto|sir|poll] [--json] [--i1] ...
# Extra args are forwarded to tools/kcp_listen.py.
#
# Darwin --setup → sudo scripts/enable-ykv-link-macos.sh
# Linux  --setup → sudo scripts/enable-ykv-link.sh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
YKV_IP="${HAVIKKI_YKV_IP:-192.168.50.11}"
MAC_IP="${HAVIKKI_MAC_IP:-192.168.50.1}"
LENOVO_IP="192.168.50.10"
UNAME="$(uname -s)"
SETUP=0
WAIT_S=12
LISTEN_ARGS=()

die() { echo "ERROR: $*" >&2; exit 1; }
info() { echo "$*"; }

usage() {
  cat <<EOF
Usage: $0 [--setup] [kcp_listen args...]

  --setup     Darwin: sudo enable-ykv-link-macos.sh
              Linux:  sudo enable-ykv-link.sh
  --help      This help

Forwarded to tools/kcp_listen.py (read-only, no T/Z):
  --once  --duration N  --mode auto|sir|poll  --json  --i1
  --host --port --timeout --wait-s --interval

YKV is ${YKV_IP}:23. One cable without a switch: Mac↔YKV or Mac↔Lenovo or Lenovo↔YKV.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --setup) SETUP=1; WAIT_S=25; shift ;;
    -h|--help) usage; exit 0 ;;
    *) LISTEN_ARGS+=("$1"); shift ;;
  esac
done

PYTHON="${HAVIKKI_PYTHON:-$(command -v python3 || true)}"
[[ -n "$PYTHON" && -x "$PYTHON" ]] || die "python3 not found"

run_as_user() {
  if [[ "$(id -u)" -eq 0 && -n "${SUDO_USER:-}" ]]; then
    sudo -u "$SUDO_USER" env PATH="$PATH" "$@"
  else
    "$@"
  fi
}

ping_once() {
  local host="$1"
  if [[ "$UNAME" == Darwin ]]; then
    ping -c 1 -W 1000 "$host" >/dev/null 2>&1
  else
    ping -c 1 -W 1 "$host" >/dev/null 2>&1
  fi
}

tcp_open() {
  local host="$1" port="$2"
  "$PYTHON" -c '
import socket, sys
host, port = sys.argv[1], int(sys.argv[2])
try:
    s = socket.create_connection((host, port), 1.5)
    s.close()
except OSError:
    sys.exit(1)
' "$host" "$port"
}

has_mac_lab_ip() {
  if [[ "$UNAME" == Darwin ]]; then
    ifconfig 2>/dev/null | grep -q "inet ${MAC_IP} "
  else
    ip -4 addr show 2>/dev/null | grep -q "inet ${MAC_IP}/"
  fi
}

if [[ "$SETUP" -eq 1 ]]; then
  setup_args=()
  if [[ -n "${HAVIKKI_IFACE:-}" ]]; then
    setup_args+=("$HAVIKKI_IFACE")
  fi
  if [[ "$UNAME" == Darwin ]]; then
    sudo "$ROOT/scripts/enable-ykv-link-macos.sh" "${setup_args[@]+"${setup_args[@]}"}"
  elif [[ "$UNAME" == Linux ]]; then
    sudo "$ROOT/scripts/enable-ykv-link.sh" "${setup_args[@]+"${setup_args[@]}"}"
  else
    die "unsupported OS: $UNAME"
  fi
fi

info "Waiting up to ${WAIT_S}s for ICMP $YKV_IP ..."
got=0
start="$(date +%s)"
while [[ $(( $(date +%s) - start )) -lt "$WAIT_S" ]]; do
  if ping_once "$YKV_IP"; then
    got=1
    break
  fi
  sleep 0.5
done

if [[ "$got" -ne 1 ]]; then
  if [[ "$UNAME" == Darwin ]]; then
    if ping_once "$LENOVO_IP" || tcp_open "$LENOVO_IP" 22 || tcp_open "$LENOVO_IP" 8080; then
      die "no YKV at $YKV_IP — cable looks like Mac↔Lenovo ($LENOVO_IP). Unplug Lenovo, CAT6 Mac↔YKV, then --setup. One cable only."
    fi
    if ! has_mac_lab_ip; then
      die "no YKV at $YKV_IP and Mac has no $MAC_IP. Plug USB-Ethernet + CAT6 to YKV, then: $0 --setup"
    fi
    die "no ICMP from $YKV_IP. YKV unpowered, DHCP lease missing, or cable not Mac↔YKV. Check /tmp/ykv-dhcp.log. Stop: sudo $ROOT/scripts/disable-ykv-link-macos.sh"
  fi
  die "no ICMP from $YKV_IP. On Linux: CAT6 Lenovo↔YKV + sudo $ROOT/scripts/enable-ykv-link.sh (or $0 --setup)"
fi

info "YKV $YKV_IP reachable — starting read-only KCP listen (no T/Z)"
run_as_user "$PYTHON" "$ROOT/tools/kcp_listen.py" --host "$YKV_IP" "${LISTEN_ARGS[@]+"${LISTEN_ARGS[@]}"}"
