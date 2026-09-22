# Mac diagnostic listen (YKV-02)

Prepare-only capability: if Ubuntu lab testing fails and the Lenovo host does not receive transmitter data, listen on **this Mac** with a **direct Ethernet cable** to the YKV-02. Use what the Mac actually receives to diagnose the Ubuntu stack.

**Do not start listening** unless the user explicitly asks in the current turn.

## Trigger phrases (this turn only)

Start only if the user says one of:

- kuuntele lähetintä
- aloita kuuntelu
- Mac suora kaapeli
- listen-ykv
- varakuuntelu

Not enough: talking about YKV, Ubuntu, dealer day, or enabling the Lenovo link.

## Topology (one cable, no switch)

Without a switch there is **one** CAT6 at a time:

| Cable | Role |
|-------|------|
| Mac ↔ Lenovo | SSH / admin UI (`192.168.50.1` ↔ `192.168.50.10`) |
| Lenovo ↔ YKV | Live kiosk stack (Ubuntu DHCP `.10` → YKV `.11`) |
| **Mac ↔ YKV** | **Diagnostic listen only** (Mac DHCP `.1` → YKV `.11:23`) |

Unplug Lenovo before Mac↔YKV. Unplug YKV before Mac↔Lenovo.

YKV-02 is a factory **DHCP client**. A direct cable with no DHCP server gives it no IP.

## Addresses

| Host | IP |
|------|----|
| Mac lab NIC | `192.168.50.1/24` — **no default gateway** (Wi-Fi keeps internet) |
| YKV | `192.168.50.11` TCP **23** KCP ASCII `\r\n` |
| Lenovo (not on this cable) | `192.168.50.10` |

DHCP on the Mac **must** bind `192.168.50.1:67` only — never `0.0.0.0` (would poison home Wi-Fi DHCP). Dummy Ethernet Adapter `en3`/`en4` are ignored unless they have carrier. Do not use Wi-Fi `en0`.

## Read-only

`tools/kcp_listen.py` may send `SIR` / `SI` / `I1` / `@` (cancel). It does **not** send `T` (tare) or `Z` (zero) unless the user later asks for that separately.

Mac listen success ≠ Ubuntu/YKV stack success. It only proves the transmitter talks KCP on the wire.

## Procedure (when explicitly asked)

1. Unplug Mac↔Lenovo. Plug USB-Ethernet (not dummy `en3`/`en4`). CAT6 Mac↔YKV. Power YKV.
2. From repo root:

```bash
sudo ./scripts/enable-ykv-link-macos.sh
# or combined:
./scripts/listen-ykv.sh --setup --mode auto --i1
```

3. Optional bounded sample: `./scripts/listen-ykv.sh --duration 20 --mode auto`
4. Single poll: `./scripts/listen-ykv.sh --once`
5. Stop DHCP + lab IP (Wi-Fi untouched): `sudo ./scripts/disable-ykv-link-macos.sh`

Env: `HAVIKKI_IFACE` (lab NIC), `HAVIKKI_MAC_IP`, `HAVIKKI_YKV_IP`.

Logs: DHCP stdout → `/tmp/ykv-dhcp.log`. Listen prints to stdout.

## Agent commands on explicit start

```bash
# 1) USB-ETH present + carrier (fail clearly if not)
# 2) sudo ./scripts/enable-ykv-link-macos.sh
# 3) ./scripts/listen-ykv.sh --mode auto --i1
#    (forward --once / --duration / --json / --mode poll|sir|auto as requested)
# 4) Report raw KCP lines. Do not claim Lenovo/live kiosk is OK.
# 5) Leave link up unless asked to stop; stop with disable-ykv-link-macos.sh
```

Wrong-cable error: ping `192.168.50.10` / TCP 22 or 8080 up, `.11` down → Mac↔Lenovo, not Mac↔YKV.

## Linux (Lenovo) counterpart

`./scripts/listen-ykv.sh --setup` runs `scripts/enable-ykv-link.sh` (dnsmasq, PC `.10`). Same `kcp_listen.py`.
