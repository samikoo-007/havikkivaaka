---
name: havikkivaaka-lab
description: >-
  Operate the Hävikkivaaka Lenovo lab (YKV-02 KCP, mock/live kiosk, offline LAN
  admin via switch, systemd boot). Use when working in havikkivaaka, or when the
  user mentions YKV, KCP, Lenovo lab, kiosk, admin UI, mock.conf, enable-ykv-link,
  192.168.50, dealer day, cloning/ISO, listen-ykv, kuuntele lähetintä, aloita
  kuuntelu, Mac suora kaapeli, or varakuuntelu. Mac diagnostic listen: NEVER
  start unless the user explicitly asks this turn.
---

# Hävikkivaaka lab

## Hard facts

| Item | Value |
|------|--------|
| Repo | `/Users/sami/Projects/havikkivaaka` (Lenovo: `~/havikkivaaka`) |
| Lab host | Lenovo E31-80 Xubuntu — **testikokoonpano only**, not production |
| Edge IP | `192.168.50.10` |
| Mac (dev/admin) | `192.168.50.1` |
| YKV | `192.168.50.11:23` KCP ASCII `\r\n` |
| HTTP | `0.0.0.0:8080` (LAN admin); kiosk Chromium uses `127.0.0.1:8080` |
| Admin URL (from Mac) | `http://192.168.50.10:8080/admin` |
| SSH | `sami@192.168.50.10` |
| Ethernet iface (Lenovo) | `enp1s0` (EEE off required) |

Without a switch: **one cable** — Mac↔Lenovo **or** Lenovo↔YKV **or** Mac↔YKV (diagnostic), not two at once.

## Mac diagnostic listen (fallback)

If Ubuntu/Lenovo does **not** receive transmitter data, diagnose on **this Mac** with a direct USB-Ethernet cable to the YKV-02. Full procedure: [`docs/mac-ykv-listen.md`](../../../docs/mac-ykv-listen.md).

**NEVER start** listen/DHCP/`listen-ykv.sh` unless the user explicitly asks **this turn**.

Trigger phrases (Finnish/English): `kuuntele lähetintä`, `aloita kuuntelu`, `Mac suora kaapeli`, `listen-ykv`, `varakuuntelu`.

On that command:

```bash
sudo ./scripts/enable-ykv-link-macos.sh          # Mac .1/24, no default gw; DHCP .11 on lab NIC only
./scripts/listen-ykv.sh --mode auto --i1         # or --setup to combine; --once / --duration / --json
# stop: sudo ./scripts/disable-ykv-link-macos.sh  # Wi-Fi untouched
```

| Item | Value |
|------|--------|
| Mac | `192.168.50.1/24` on USB/TB Ethernet (**not** Wi-Fi `en0`) |
| YKV | `192.168.50.11:23` |
| DHCP | Python `tools/ykv_dhcp.py` bind **only** `.1:67` (never `0.0.0.0`) |
| Listen | `tools/kcp_listen.py` read-only (`SI`/`SIR`/`I1`) — no `T`/`Z` unless asked |

Mac listen success is **not** Ubuntu/YKV stack success — it only proves the transmitter talks KCP on the wire. USB-ETH may be unplugged; dummy `en3`/`en4` are ignored without carrier.

## Read first (progressive)

- Architecture + mock/live: [`system_architecture.md`](../../../system_architecture.md)
- **Deploy / monista kiosk mihin tahansa Xubuntuun:** [`havikkivaaka-kiosk-deploy`](../havikkivaaka-kiosk-deploy/SKILL.md)
- **New YKV + platform commission / SAD cal:** [`ykv-commissioning`](../ykv-commissioning/SKILL.md)
- Phases (test → clean Ubuntu → final UI → clone/ISO): [`docs/roadmap-deployment.md`](../../../docs/roadmap-deployment.md)
- Dealer checklist: [`docs/dealer-day-checklist.md`](../../../docs/dealer-day-checklist.md)
- Mac diagnostic listen (opt-in): [`docs/mac-ykv-listen.md`](../../../docs/mac-ykv-listen.md)
- KCP model: [`docs/kcp-protocol-model.md`](../../../docs/kcp-protocol-model.md)
- Admin backlog: [`docs/admin-backlog-agentti2.md`](../../../docs/admin-backlog-agentti2.md)
- Kiosk backlog: [`docs/kiosk-kilpailija-esitys.md`](../../../docs/kiosk-kilpailija-esitys.md)

## Phase rules

1. **Now:** validate YKV read + stack on Lenovo. Do **not** claim physical YKV end-to-end OK until live cable test passes.
2. **Repo duty:** every lab install step must live in scripts (`bootstrap-xubuntu.sh`, `enable-ykv-link.sh`, `install-kiosk-autostart.sh`, …) so a **clean Ubuntu** can match the lab.
3. **After YKV OK:** finalize kiosk + admin UX (backlogs).
4. **When lab done:** clone via scripts; optionally Clonezilla / custom ISO → bootable USB (`roadmap-deployment.md` §4).

## Roles (same process)

| Surface | Path | May write |
|---------|------|-----------|
| Kiosk | `/` | `/api/state` read; protected tare/reset only |
| Admin | `/admin` | config, reports, health, export — via switch/LAN PC |

No dual-HDMI requirement on edge. Offline = local switch, no cloud.

## Mock vs live

**Check before diagnosing UI:**

```bash
curl -s http://127.0.0.1:8080/api/state   # on Lenovo
# or from Mac:
curl -s http://192.168.50.10:8080/api/state
```

Expect `"mode":"mock"|"live"`, `"connected"`, `"error"`.

| Mode | How |
|------|-----|
| Mock (UI work, no YKV) | drop-in `havikki-kiosk-app.service.d/mock.conf`; stop/disable `havikki-ykv-link`; Mac cable OK |
| Live YKV | remove mock.conf; enable `havikki-ykv-link` + `havikki-kiosk-app`; CAT6 to YKV at dealer boot |

**Lenovo dealer-ready (default):** no mock drop-in; both units enabled; app `mode=live` → `192.168.50.11:23`. Without YKV cable, `connected=false` is OK until dealer power-up.

## Common commands

```bash
# Clean-ish host packages
sudo ./scripts/bootstrap-xubuntu.sh

# Boot kiosk (systemd + LightDM + Chromium)
sudo ./scripts/install-kiosk-autostart.sh

# Manual
./scripts/start-kiosk.sh              # mock
./scripts/start-kiosk.sh --live       # YKV
sudo ./scripts/enable-ykv-link.sh     # DHCP .11 + EEE
sudo ./scripts/disable-ykv-link.sh    # free cable for Mac SSH

# Mac diagnostic listen — ONLY if user explicitly asked this turn
sudo ./scripts/enable-ykv-link-macos.sh
./scripts/listen-ykv.sh --mode auto --i1
sudo ./scripts/disable-ykv-link-macos.sh

# Sync Mac → Lenovo (exclude data/logs)
rsync -az --exclude '.git' --exclude 'data/' --exclude 'logs/' \
  --exclude '__pycache__' ./ sami@192.168.50.10:~/havikkivaaka/
```

Env overrides: `HAVIKKI_IFACE`, `HAVIKKI_HOST`, `HAVIKKI_HTTP_HOST`, `HAVIKKI_HTTP_PORT`, `HAVIKKI_USER`.

## Agent do / don't

**Do**

- Prefer scripts + docs over one-off SSH edits; if you change Lenovo systemd, mirror into repo scripts.
- Update `system_architecture.md` when adding services, cron, or DB connections.
- Investigate logs (`docker` N/A; use `journalctl` / `logs/kiosk-app.log`) before guessing failures.
- Redact secrets; never commit `.env` or KCP vendor PDF.

**Don't**

- Treat Lenovo as production golden image until roadmap phase 4.
- Ship final kiosk/admin layout as “done” before live YKV sign-off.
- Bind admin to `127.0.0.1` only if LAN admin via switch is required (`0.0.0.0` is the agreed default).
- Confuse mock success with YKV hardware success.
- Confuse **Mac listen success** with Ubuntu/YKV stack success — Mac listen is diagnostic fallback only.
- Start Mac↔YKV listen, DHCP, or `listen-ykv.sh` unless the user explicitly asked this turn.

## Quick triage

| Symptom | Likely cause |
|---------|----------------|
| Mac `127.0.0.1:8080` fails | App is on Lenovo; use `192.168.50.10:8080` (needs bind `0.0.0.0`) |
| `192.168.50.10` admin fails | Still bound to localhost, or service down |
| Ethernet flaps | EEE on Realtek — `ethtool --set-eee enp1s0 eee off` / boot script |
| No YKV lease | Cable is Mac, or `havikki-ykv-link` stopped, or YKV unpowered at boot |
| UI connected but mode mock | Expected with `mock.conf`; not a live scale |
| Ubuntu gets no YKV data | Fallback: Mac↔YKV listen (`docs/mac-ykv-listen.md`) — does not prove Lenovo stack |
