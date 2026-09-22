#!/usr/bin/env bash
# Tear down direct YKV link (dnsmasq + restore NetworkManager on iface).
# Usage: sudo ./scripts/disable-ykv-link.sh [IFACE]

set -euo pipefail

IFACE="${1:-}"
DNSMASQ_PID="/tmp/ykv-dnsmasq.pid"

[[ "$(id -u)" -eq 0 ]] || { echo "Run as: sudo $0"; exit 1; }

if [[ -z "$IFACE" ]]; then
  IFACE="$(ip -o link show | awk -F': ' '/^[0-9]+: (en|eth)/{print $2; exit}')"
  IFACE="${IFACE:-enp1s0}"
fi

if [[ -f "$DNSMASQ_PID" ]] && kill -0 "$(cat "$DNSMASQ_PID")" 2>/dev/null; then
  kill "$(cat "$DNSMASQ_PID")" || true
  rm -f "$DNSMASQ_PID"
  echo "dnsmasq stopped"
fi

rm -f /tmp/ykv-dnsmasq.conf /tmp/ykv-dnsmasq.leases

if command -v nmcli >/dev/null 2>&1; then
  nmcli dev set "$IFACE" managed yes 2>/dev/null || true
  echo "NetworkManager managing $IFACE again"
fi

echo "YKV link disabled on $IFACE"
