#!/usr/bin/env bash
# Configure laptop Ethernet for direct YKV-02 link + DHCP for the transmitter.
# Usage: sudo ./scripts/enable-ykv-link.sh [IFACE]
# Default IFACE: first connected ethernet-like link, else eth0.
#
# SAFETY: refuses to start if the chosen iface carries a default route
# (looks like the site/office LAN). YKV DHCP must stay on an isolated cable.
# Override only for deliberate lab tests: HAVIKKI_ALLOW_DHCP_ON_DEFAULTED_IFACE=1

set -euo pipefail

IFACE="${1:-}"
PC_IP="192.168.50.10"
PC_CIDR="24"
YKV_IP="192.168.50.11"
DNSMASQ_CONF="/tmp/ykv-dnsmasq.conf"
DNSMASQ_PID="/tmp/ykv-dnsmasq.pid"
DNSMASQ_LEASES="/tmp/ykv-dnsmasq.leases"

die() { echo "ERROR: $*" >&2; exit 1; }
need() { command -v "$1" >/dev/null || die "missing command: $1 (apt install $1)"; }

[[ "$(id -u)" -eq 0 ]] || die "run as root: sudo $0"

need ip
need dnsmasq

if [[ -z "$IFACE" ]]; then
  IFACE="$(ip -o link show | awk -F': ' '/^[0-9]+: (en|eth)/{print $2; exit}')"
  IFACE="${IFACE:-eth0}"
fi

ip link show "$IFACE" >/dev/null || die "interface not found: $IFACE"
echo "Using interface: $IFACE"

# Refuse DHCP on an iface that is the machine's default gateway path
# (would poison a shared school/office LAN).
if [[ "${HAVIKKI_ALLOW_DHCP_ON_DEFAULTED_IFACE:-}" != "1" ]]; then
  if ip -4 route show default 2>/dev/null | grep -Eq "[[:space:]]dev[[:space:]]${IFACE}([[:space:]]|$)"; then
    die "refusing DHCP on $IFACE: it has a default route (looks like site LAN). Use a dedicated cable to YKV only, or set HAVIKKI_ALLOW_DHCP_ON_DEFAULTED_IFACE=1 for a deliberate lab exception."
  fi
  if ip -4 route show default dev "$IFACE" 2>/dev/null | grep -q .; then
    die "refusing DHCP on $IFACE: default route via this iface. Isolated YKV link only."
  fi
fi

ip link set "$IFACE" up

# Prefer keeping an existing PC_IP (avoids brief SSH drops on live install).
if ip -4 addr show dev "$IFACE" | grep -q "inet ${PC_IP}/"; then
  echo "Address ${PC_IP} already present on $IFACE"
else
  ip addr flush dev "$IFACE" || true
  ip addr add "${PC_IP}/${PC_CIDR}" dev "$IFACE"
fi

# Stop conflicting DHCP clients on this iface if present
if command -v nmcli >/dev/null 2>&1; then
  nmcli dev set "$IFACE" managed no 2>/dev/null || true
fi

cat >"$DNSMASQ_CONF" <<EOF
interface=$IFACE
bind-interfaces
dhcp-range=$YKV_IP,$YKV_IP,255.255.255.0,1h
dhcp-option=3,$PC_IP
dhcp-leasefile=$DNSMASQ_LEASES
log-dhcp
EOF

if [[ -f "$DNSMASQ_PID" ]] && kill -0 "$(cat "$DNSMASQ_PID")" 2>/dev/null; then
  kill "$(cat "$DNSMASQ_PID")" || true
  sleep 0.5
fi
rm -f "$DNSMASQ_PID" "$DNSMASQ_LEASES"

dnsmasq --conf-file="$DNSMASQ_CONF" --pid-file="$DNSMASQ_PID"
echo "dnsmasq started — waiting for YKV DHCP lease at $YKV_IP (iface=$IFACE only)"
echo "Then:  printf 'SI\\r\\n' | nc -v $YKV_IP 23"
echo "Or:    python3 tools/kcp_client.py --host $YKV_IP si"
echo "Stop:  sudo kill \$(cat $DNSMASQ_PID); sudo nmcli dev set $IFACE managed yes"
