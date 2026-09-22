#!/usr/bin/env bash
# Configure Mac USB/Thunderbolt Ethernet for a direct YKV-02 diagnostic link.
# Usage: sudo ./scripts/enable-ykv-link-macos.sh [IFACE]
# Env: HAVIKKI_IFACE, HAVIKKI_MAC_IP (default 192.168.50.1), HAVIKKI_YKV_IP,
#      HAVIKKI_PYTHON
#
# Sets 192.168.50.1/24 on the lab NIC WITHOUT a default gateway (Wi-Fi keeps
# internet). DHCP binds only that lab IP:67 — never 0.0.0.0 / Wi-Fi.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MAC_IP="${HAVIKKI_MAC_IP:-192.168.50.1}"
YKV_IP="${HAVIKKI_YKV_IP:-192.168.50.11}"
MASK="255.255.255.0"
PID_FILE="/tmp/ykv-dhcp.pid"
IFACE_FILE="/tmp/ykv-link.iface"
DHCP_LOG="/tmp/ykv-dhcp.log"
IFACE="${1:-${HAVIKKI_IFACE:-}}"

die() { echo "ERROR: $*" >&2; exit 1; }
info() { echo "$*" >&2; }

[[ "$(uname -s)" == Darwin ]] || die "this script is for macOS (use scripts/enable-ykv-link.sh on Linux)"
[[ "$(id -u)" -eq 0 ]] || die "run as root: sudo $0"

PYTHON="${HAVIKKI_PYTHON:-$(command -v python3 || true)}"
[[ -n "$PYTHON" && -x "$PYTHON" ]] || die "python3 not found"

list_hw_ports() {
  networksetup -listallhardwareports 2>/dev/null | awk '
    /^Hardware Port: / {
      port = $0
      sub(/^Hardware Port: /, "", port)
    }
    /^Device: / { print $2 "\t" port }
  '
}

port_kind() {
  local lname
  lname="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')"
  case "$lname" in
    wi-fi|wifi|airport) echo skip ;;
    bluetooth*|iphone*|ipad*) echo skip ;;
    *bridge*) echo skip ;;
    usb*|*" usb "*|*10/100*|thunderbolt\ ethernet*) echo prefer ;;
    thunderbolt*) echo skip ;;
    ethernet\ adapter*) echo dummy ;;
    *) echo other ;;
  esac
}

iface_exists() { ifconfig "$1" >/dev/null 2>&1; }

iface_active() {
  ifconfig "$1" 2>/dev/null | grep -q 'status: active'
}

iface_media_none() {
  ifconfig "$1" 2>/dev/null | grep -q 'media: none'
}

port_name_for() {
  local dev="$1" line name
  while IFS=$'\t' read -r ifc name; do
    if [[ "$ifc" == "$dev" ]]; then
      printf '%s' "$name"
      return 0
    fi
  done < <(list_hw_ports)
  return 1
}

refuse_wifi() {
  local dev="$1" name kind
  name="$(port_name_for "$dev" || true)"
  kind="$(port_kind "${name:-}")"
  if [[ "$kind" == skip ]]; then
    die "refusing $dev (${name:-unknown}) — keep Wi-Fi/Thunderbolt for internet; use USB-Ethernet to YKV"
  fi
  if [[ "$dev" == en0 ]]; then
    die "refusing en0 (Wi-Fi on this Mac). Plug USB-Ethernet; do not put lab DHCP on Wi-Fi."
  fi
}

validate_candidate() {
  local dev="$1" name kind
  iface_exists "$dev" || die "interface not found: $dev"
  name="$(port_name_for "$dev" || true)"
  kind="$(port_kind "${name:-other}")"
  refuse_wifi "$dev"
  if [[ "$kind" == dummy ]] && iface_media_none "$dev"; then
    die "$dev is dummy Ethernet Adapter (${name}) with no media — ignored. Plug USB-Ethernet."
  fi
  if ! iface_active "$dev"; then
    die "$dev (${name:-unknown}) has no carrier. Plug CAT6 Mac↔YKV (YKV powered), not Mac↔Lenovo."
  fi
}

detect_iface() {
  local ifc name kind
  local -a prefer_active=() prefer_down=() dummy_active=()

  while IFS=$'\t' read -r ifc name; do
    [[ -n "$ifc" ]] || continue
    kind="$(port_kind "$name")"
    case "$kind" in
      skip) info "skip $ifc ($name)" ;;
      prefer)
        if iface_active "$ifc"; then
          prefer_active+=("$ifc")
          info "candidate $ifc ($name) carrier=yes"
        else
          prefer_down+=("$ifc")
          info "candidate $ifc ($name) carrier=no"
        fi
        ;;
      dummy)
        if iface_active "$ifc" && ! iface_media_none "$ifc"; then
          dummy_active+=("$ifc")
          info "dummy $ifc ($name) has carrier — allowing"
        else
          info "ignore dummy $ifc ($name) (no carrier)"
        fi
        ;;
      *) info "ignore $ifc ($name)" ;;
    esac
  done < <(list_hw_ports)

  if ((${#prefer_active[@]} == 1)); then
    echo "${prefer_active[0]}"
    return 0
  fi
  if ((${#prefer_active[@]} > 1)); then
    info "multiple USB/TB Ethernet ifaces with carrier: ${prefer_active[*]}"
    echo "${prefer_active[0]}"
    return 0
  fi
  if ((${#dummy_active[@]} >= 1)); then
    echo "${dummy_active[0]}"
    return 0
  fi
  if ((${#prefer_down[@]} >= 1)); then
    die "USB/Thunderbolt Ethernet found (${prefer_down[*]}) but no link. Plug CAT6 Mac↔YKV (YKV powered). Dummy en3/en4 are ignored without carrier."
  fi
  die "No USB-Ethernet / Thunderbolt Ethernet adapter found.
This Mac keeps internet on Wi-Fi (en0). Dummy Ethernet Adapter en3/en4 are ignored unless they have carrier.
Plug the USB-Ethernet dongle, CAT6 to YKV-02 (not Lenovo), then re-run.
Override: sudo HAVIKKI_IFACE=enX $0"
}

if [[ -z "$IFACE" ]]; then
  IFACE="$(detect_iface)"
else
  info "Using HAVIKKI_IFACE/arg: $IFACE"
  validate_candidate "$IFACE"
fi

refuse_wifi "$IFACE"
validate_candidate "$IFACE"
info "Using lab NIC: $IFACE ($(port_name_for "$IFACE" || echo unknown))"

ifconfig "$IFACE" up || die "failed to bring $IFACE up"

# Drop leftover addresses on the lab NIC only (never Wi-Fi).
while read -r old_ip; do
  [[ -n "$old_ip" && "$old_ip" != "$MAC_IP" ]] || continue
  info "removing leftover $old_ip from $IFACE"
  ifconfig "$IFACE" inet "$old_ip" delete || true
done < <(ifconfig "$IFACE" | awk '/inet /{print $2}')

if ifconfig "$IFACE" | grep -q "inet ${MAC_IP} "; then
  info "Address $MAC_IP already on $IFACE"
else
  ifconfig "$IFACE" inet "$MAC_IP" netmask "$MASK" || die "failed to set $MAC_IP on $IFACE"
fi

# Prefer ifconfig-only addressing. `ipconfig set MANUAL` on some macOS versions
# briefly drops the inet address and made confirm fail even when .1 was already set.
if ! ifconfig "$IFACE" | grep -q "inet ${MAC_IP} "; then
  ifconfig "$IFACE" inet "$MAC_IP" netmask "$MASK" || die "failed to confirm $MAC_IP on $IFACE"
fi
if ! ifconfig "$IFACE" | grep -q "inet ${MAC_IP} "; then
  die "failed to confirm $MAC_IP on $IFACE"
fi

# Ensure no default gateway on the lab NIC (Wi-Fi keeps internet).
ipconfig set "$IFACE" MANUAL "$MAC_IP" "$MASK" 2>/dev/null || true
# Re-assert address if ipconfig cleared it.
if ! ifconfig "$IFACE" | grep -q "inet ${MAC_IP} "; then
  info "re-applying $MAC_IP after ipconfig"
  ifconfig "$IFACE" inet "$MAC_IP" netmask "$MASK" || die "failed to restore $MAC_IP on $IFACE"
fi

# If macOS added a default via the lab NIC, delete it. Wi-Fi must keep internet.
if route -n get default -ifscope "$IFACE" >/dev/null 2>&1; then
  info "removing ifscope default on $IFACE (must not steal Wi-Fi gateway)"
  route -n delete default -ifscope "$IFACE" 2>/dev/null || true
fi
if netstat -rn -f inet | awk -v ip="$MAC_IP" -v ifc="$IFACE" '
  $1=="default" && ($2==ip || $NF==ifc) { found=1 }
  END { exit found?0:1 }
'; then
  info "removing default route via lab NIC"
  route -n delete default "$MAC_IP" 2>/dev/null || true
fi

DEF_IF="$(route -n get default 2>/dev/null | awk '/interface:/{print $2; exit}')"
info "Default route interface: ${DEF_IF:-none} (Wi-Fi en0 must stay for internet)"
if [[ "${DEF_IF:-}" == "$IFACE" ]]; then
  die "default gateway would leave via lab NIC $IFACE — aborting so Wi-Fi internet is kept"
fi

# Reuse healthy existing DHCP on lab IP first (avoids fighting a live bind).
EXISTING_DHCP_PID="$(ps aux | awk '/[y]kv_dhcp\.py/ {print $2; exit}')"
if [[ -n "$EXISTING_DHCP_PID" ]]; then
  if lsof -nP -iUDP@${MAC_IP}:67 2>/dev/null | grep -q . || \
     lsof -nP -iUDP:67 2>/dev/null | grep -qE "ykv_dhcp|Python"; then
    info "Reusing existing ykv_dhcp pid=$EXISTING_DHCP_PID (already bound ${MAC_IP}:67)"
    printf '%s\n' "$EXISTING_DHCP_PID" >"$PID_FILE"
    printf '%s\n' "$IFACE" >"$IFACE_FILE"
    info "Mac ${MAC_IP}/24 on $IFACE (no default gateway added)"
    info "DHCP offering $YKV_IP via ${MAC_IP}:67 pid=$EXISTING_DHCP_PID log=$DHCP_LOG"
    info "Wi-Fi left alone. One cable: Mac↔YKV (not Mac↔Lenovo)."
    info "Next (do not auto-start): ./scripts/listen-ykv.sh"
    info "Stop: sudo ./scripts/disable-ykv-link-macos.sh"
    exit 0
  fi
fi

if [[ -f "$PID_FILE" ]]; then
  OLD_PID="$(tr -d '[:space:]' < "$PID_FILE" || true)"
  if [[ -n "$OLD_PID" ]] && kill -0 "$OLD_PID" 2>/dev/null; then
    info "stopping previous ykv_dhcp pid=$OLD_PID"
    kill "$OLD_PID" || true
    sleep 0.4
  fi
  rm -f "$PID_FILE"
fi
pkill -f "tools/ykv_dhcp.py" 2>/dev/null || true
pkill -f "ykv_dhcp.py" 2>/dev/null || true
sleep 0.5
rm -f "$PID_FILE"

if command -v lsof >/dev/null 2>&1; then
  if lsof -nP -iUDP@${MAC_IP}:67 2>/dev/null | grep -q . || \
     lsof -nP -iUDP:67 2>/dev/null | grep -q .; then
    info "UDP ${MAC_IP}:67 still in use after pkill — kill -9 ykv_dhcp PIDs"
    ps aux | awk '/ykv_dhcp\.py/ && !/awk/ {print $2}' | while read -r p; do
      kill -9 "$p" 2>/dev/null || true
    done
    sleep 0.4
  fi
fi

: >"$DHCP_LOG"
nohup "$PYTHON" "$ROOT/tools/ykv_dhcp.py" \
  --foreground \
  --server-ip "$MAC_IP" \
  --offer-ip "$YKV_IP" \
  --mask "$MASK" \
  --pid-file "$PID_FILE" >>"$DHCP_LOG" 2>&1 &

ok=0
for _ in $(seq 1 20); do
  if [[ -f "$PID_FILE" ]]; then
    NEW_PID="$(tr -d '[:space:]' < "$PID_FILE" || true)"
    if [[ -n "$NEW_PID" ]] && kill -0 "$NEW_PID" 2>/dev/null; then
      ok=1
      break
    fi
  fi
  sleep 0.15
done

if [[ "$ok" -ne 1 ]]; then
  echo "DHCP log ($DHCP_LOG):" >&2
  cat "$DHCP_LOG" >&2 || true
  die "DHCP did not start (need root bind ${MAC_IP}:67, never 0.0.0.0). Try: sudo kill -9 \$(pgrep -f ykv_dhcp.py); sudo $0 $IFACE"
fi

printf '%s\n' "$IFACE" >"$IFACE_FILE"
NEW_PID="$(tr -d '[:space:]' < "$PID_FILE")"
info "Mac ${MAC_IP}/24 on $IFACE (no default gateway added)"
info "DHCP offering $YKV_IP via ${MAC_IP}:67 pid=$NEW_PID log=$DHCP_LOG"
info "Wi-Fi left alone. One cable: Mac↔YKV (not Mac↔Lenovo)."
info "Next (do not auto-start): ./scripts/listen-ykv.sh"
info "Stop: sudo ./scripts/disable-ykv-link-macos.sh"
