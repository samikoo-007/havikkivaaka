#!/usr/bin/env bash
# Tear down Mac diagnostic YKV link (Python DHCP + 192.168.50.1 on lab NIC).
# Usage: sudo ./scripts/disable-ykv-link-macos.sh [IFACE]
# Env: HAVIKKI_IFACE, HAVIKKI_MAC_IP
# Does not touch Wi-Fi.

set -euo pipefail

MAC_IP="${HAVIKKI_MAC_IP:-192.168.50.1}"
PID_FILE="/tmp/ykv-dhcp.pid"
IFACE_FILE="/tmp/ykv-link.iface"
IFACE="${1:-${HAVIKKI_IFACE:-}}"

die() { echo "ERROR: $*" >&2; exit 1; }
info() { echo "$*"; }

[[ "$(uname -s)" == Darwin ]] || die "this script is for macOS (use scripts/disable-ykv-link.sh on Linux)"
[[ "$(id -u)" -eq 0 ]] || die "run as root: sudo $0"

if [[ -z "$IFACE" && -f "$IFACE_FILE" ]]; then
  IFACE="$(tr -d '[:space:]' < "$IFACE_FILE" || true)"
fi

if [[ -z "$IFACE" ]]; then
  IFACE="$(ifconfig 2>/dev/null | awk -v ip="$MAC_IP" '
    /^[a-z0-9]+:/ { iface=$1; sub(/:$/, "", iface) }
    $1=="inet" && $2==ip { print iface; exit }
  ' || true)"
fi

if [[ -n "$IFACE" && "$IFACE" == en0 ]]; then
  die "refusing to modify en0 (Wi-Fi). Check $IFACE_FILE / HAVIKKI_IFACE."
fi

if [[ -f "$PID_FILE" ]]; then
  PID="$(tr -d '[:space:]' < "$PID_FILE" || true)"
  if [[ -n "$PID" ]] && kill -0 "$PID" 2>/dev/null; then
    kill "$PID" || true
    sleep 0.3
    if kill -0 "$PID" 2>/dev/null; then
      kill -9 "$PID" || true
    fi
    info "ykv_dhcp stopped (pid $PID)"
  else
    info "no running ykv_dhcp for $PID_FILE"
  fi
  rm -f "$PID_FILE"
else
  info "no $PID_FILE"
fi

if [[ -n "$IFACE" ]] && ifconfig "$IFACE" >/dev/null 2>&1; then
  if ifconfig "$IFACE" | grep -q "inet ${MAC_IP} "; then
    ifconfig "$IFACE" inet "$MAC_IP" delete || true
    info "removed $MAC_IP from $IFACE"
  else
    info "$MAC_IP not present on $IFACE"
  fi
elif [[ -n "$IFACE" ]]; then
  info "interface $IFACE gone (dongle unplugged?) — skipped address delete"
else
  info "lab iface unknown — DHCP stopped; Wi-Fi untouched"
fi

rm -f "$IFACE_FILE"
info "Mac YKV link disabled (Wi-Fi not changed)"
