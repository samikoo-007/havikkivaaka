#!/usr/bin/env bash
# Boot wrapper: disable EEE on wired iface, then start YKV DHCP link (dnsmasq).
# Usage: sudo ./scripts/havikki-boot-ykv.sh [IFACE]
# Intended for systemd oneshot havikki-ykv-link.service.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
IFACE="${1:-enp1s0}"
LOG_DIR="${HAVIKKI_LOG_DIR:-/tmp}"
LOG="${LOG_DIR}/havikki-boot-ykv.log"
mkdir -p "$LOG_DIR"

exec >>"$LOG" 2>&1
echo "==== $(date -Is) havikki-boot-ykv iface=$IFACE ===="

[[ "$(id -u)" -eq 0 ]] || { echo "ERROR: run as root"; exit 1; }

# Wait until iface exists (USB-Ethernet / PCI ready)
for _ in $(seq 1 60); do
  if ip link show "$IFACE" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
ip link show "$IFACE" >/dev/null || { echo "ERROR: interface missing: $IFACE"; exit 1; }

ip link set "$IFACE" up || true

# Wait briefly for carrier (YKV may be powered later — do not fail)
for _ in $(seq 1 15); do
  if [[ "$(cat /sys/class/net/"$IFACE"/carrier 2>/dev/null || echo 0)" == "1" ]]; then
    echo "carrier up on $IFACE"
    break
  fi
  sleep 1
done

if command -v ethtool >/dev/null 2>&1; then
  if ethtool --set-eee "$IFACE" eee off 2>/dev/null; then
    echo "EEE disabled via ethtool on $IFACE"
  else
    echo "WARN: ethtool --set-eee failed (unsupported or already off)"
  fi
  ethtool --show-eee "$IFACE" 2>/dev/null || true
else
  echo "WARN: ethtool not installed"
fi

exec "$ROOT/scripts/enable-ykv-link.sh" "$IFACE"
