# Hävikkivaaka — system architecture

## Goal
Customer plate-waste weighing: KFP → **YKV-02** → Ethernet KCP → host → kiosk UI (smile/ok/frown).

**Hankinta / kokoonpano-suositus (KERN via Prodi):** [`docs/kokoonpano-suositus.md`](docs/kokoonpano-suositus.md) — ostopaikka [prodi.fi](https://prodi.fi/).

Product feature gaps vs competitors (admin + kiosk backlog): [`docs/kilpailija-ominaisuusanalyysi.md`](docs/kilpailija-ominaisuusanalyysi.md).

**Lifecycle / phases (test → clean Ubuntu → final UI → clone):** [`docs/roadmap-deployment.md`](docs/roadmap-deployment.md).

## Project status (phases)

| Phase | Meaning |
|-------|---------|
| **Now** | **Testikokoonpano only** — Lenovo lab validates YKV read/operation + software. Not a production appliance. |
| **Repo duty** | Everything proven on the lab host must be reproducible on a **clean Ubuntu** machine via repo scripts (`bootstrap-xubuntu.sh`, `install-kiosk-autostart.sh`, …). |
| **After YKV OK** | Final kiosk + admin UX/features (backlogs), still developed against the validated stack. |
| **When lab is “done”** | Clone to another machine: scripted install (always) and/or **Clonezilla image / custom ISO → bootable USB** — see roadmap §4. |

## Deployment (target): offline LAN + admin via switch

Fully offline: no cloud, no internet. One edge host runs the API + guest kiosk display; staff open admin from another machine on the same local switch.

```text
[YKV-02 A/B] --CAT6--+--[switch]--[Kiosk/edge PC or Pi]
                     |              HTTP 0.0.0.0:8080
                     |              Chromium kiosk → http://127.0.0.1:8080/
                     |
                     +-------------[Admin PC / laptop]
                                    Browser → http://<edge-ip>:8080/admin
```

| Role | Device | Notes |
|------|--------|--------|
| Edge (palvelin + kiosk-näyttö) | miniPC / Raspberry Pi / lab Lenovo | One display is enough; Chromium kiosk on localhost |
| Admin client | Separate PC on switch | `http://<edge-lan-ip>:8080/admin` — reports, thresholds, health, config write |
| Scales | YKV-02 on same switch (or direct to edge) | KCP TCP **23** |

**Software split (same process):** kiosk reads `GET /api/state` (+ protected tare/reset); admin writes config / reads reports. Not two HDMI outputs on one box.

**Bind:** HTTP listens on `0.0.0.0:8080` (env `HAVIKKI_HTTP_HOST`). Intended for isolated site LAN only (admin auth still backlog).

## Lab (now) — testikokoonpano only
| Role | Device | Notes |
|------|--------|--------|
| Host | Lenovo E31-80, **Xubuntu / Ubuntu 26.04** | `~/havikkivaaka`, edge IP `192.168.50.10` — **YKV + softan testi, ei tuotanto** |
| Dev / admin link | Mac `192.168.50.1` ↔ Lenovo `192.168.50.10` | USB-Ethernet or switch; admin `http://192.168.50.10:8080/admin` |
| Dealer link | Lenovo `192.168.50.10` ↔ YKV `192.168.50.11` | CAT6 + `enable-ykv-link.sh` DHCP |
| Scale | **0–3×** YKV-02 (max 3; skeema laajennettavissa) | TCP **23** KCP. Sallitut: **A** \| **A+B** \| **A+C** \| **A+B+C** \| **C**. Hostit Admin UI:sta (`scale_*_host` / port). **A** = vasen lohko (yksin tai A+C → kiosk full-width); **B** = oikea lohko; **C** = keittiön hävikki (data only, ei palautetta, tilastot erillään; vain C → **ei kiosk-tilaa**). SAD cal per enabled scale. |

Lab without switch: one Ethernet cable at a time (Mac↔Lenovo **or** Lenovo↔YKV **or** Mac↔YKV diagnostic). With switch: Mac + YKV + edge can share the LAN.

**Mac diagnostic listen (fallback, not the live stack):** if Lenovo does not receive transmitter data, CAT6 Mac↔YKV (unplug Lenovo). Mac `192.168.50.1/24` on USB-Ethernet (**no default gateway**; Wi-Fi keeps internet), Python DHCP offers `.11` bound **only** to `.1:67` (never `0.0.0.0`). Read-only KCP: `scripts/listen-ykv.sh` → `tools/kcp_listen.py`. Procedure: [`docs/mac-ykv-listen.md`](docs/mac-ykv-listen.md). Do not start unless explicitly asked. Mac listen success ≠ Ubuntu stack success.

**Clean Ubuntu target:** same behaviour via repo install path in [`docs/roadmap-deployment.md`](docs/roadmap-deployment.md) §2 — do not rely on Lenovo-only manual steps.

## Software
- `app/server.py` — poll `SI`, state machine, SQLite, HTTP kiosk + admin API
- `app/config.py` — `data/config.json` (thresholds, theme, export flags, smile/frown texts); hot-reload on save
- `app/static/index.html` — diner kiosk vain kun A tai A+B (A = full-width; A+B = split); C ei diner-UI; 3-tier feedback A/B; day stats min_g (A+B); mock demo; `data-theme`
- `app/static/admin.html` — settings, reports, health; backlog: layouts A/A+B/A+B+C/C, hostit UI:sta, C erilliset tilastot, (i)-hover ohjeet
- `data/exports/` — auto/manual day reports (`day-YYYY-MM-DD-*.csv|.json`)
- `scripts/start-kiosk.sh` — `--mock` / `--live` / `--live --browser-only` (Chromium when systemd owns the app)
- `scripts/havikki-boot-ykv.sh` + `havikki-ykv-link.service` — EEE off + `enable-ykv-link.sh` (dnsmasq → `.11`)
- `scripts/enable-ykv-link-macos.sh` / `disable-ykv-link-macos.sh` — Mac lab NIC `.1/24` (no default gw) + `tools/ykv_dhcp.py` (bind `.1:67` only)
- `scripts/listen-ykv.sh` + `tools/kcp_listen.py` — read-only KCP listen (Mac or Linux); no tare/zero
- `havikki-kiosk-app.service` — live `python3 -m app.server` as user `sami`, `Restart=always`
- `scripts/install-kiosk-autostart.sh` — units + LightDM autologin + XFCE autostart
- `scripts/install-power-schedule.sh` — evening day-close timer + boot ensure + RTC helpers ([`docs/power-schedule.md`](docs/power-schedule.md))
- `scripts/havikki-day-close.sh` / `havikki-day-boot-ensure.sh` / `havikki-rtc-wake.sh` — export+reset, missed-close safety, RTC wakealarm
- `tools/kcp_mock.py` — fake YKV over TCP (default `:2323`); optional HTTP control `:2324` (`POST /set`, `/add`, `/zero`) so Mac can emulate scale for Lenovo over USB-Ethernet
- No Docker on lab host

### Boot flow (dealer kiosk)
1. `network-online` → `havikki-ykv-link` (EEE + DHCP for YKV)
2. `havikki-kiosk-app` → HTTP `0.0.0.0:8080`, KCP `192.168.50.11:23`
3. `havikki-day-boot-ensure` (oneshot) — missed evening close
4. LightDM autologin `sami` → autostart Chromium kiosk (`--browser-only`)
5. Evening: `havikki-day-close.timer` → export+reset → RTC wake → `poweroff` (YKV/näyttö katkaisija erikseen)

### Lab UI mode (mock, no YKV)
Temporary override when working on dashboard without scale (not for dealer boot):

- Drop-in: `/etc/systemd/system/havikki-kiosk-app.service.d/mock.conf`  
  → `python3 -m app.server --mock --http-host 0.0.0.0 --http-port 8080 --settle-s 2`
- `havikki-ykv-link.service`: **stopped + disabled** (and optional `systemctl mask --runtime` until reboot)
- Base unit may have `Wants=havikki-ykv-link` removed while mock is active; live backup: `havikki-kiosk-app.service.bak-live`
- Check: `curl -s http://127.0.0.1:8080/api/state` → `"mode":"mock"`, `"connected":true`, `"error":null`
- Chromium still `http://127.0.0.1:8080/` (local); admin from Mac: `http://192.168.50.10:8080/admin`

**Dealer / live boot (current default on Lenovo):** no `mock.conf`; both `havikki-ykv-link` and `havikki-kiosk-app` **enabled**. On boot: DHCP for YKV `.11`, app `--host 192.168.50.11 --port 23 --http-host 0.0.0.0`. Without YKV cable, `mode=live` and `connected=false` is expected.

### Daily power schedule (lukittu 2026-09-22)

Tuotantotavoite: automaattinen päivärytmi ilman pilveä.

| Komponentti | Toiminta | Toteutus |
|-------------|----------|----------|
| **Edge Ubuntu** | Sammutus illalla (esim. 18:00); käynnistys aamulla (esim. 08:00) | Softa: `systemd` timer → `poweroff`. Käynnistys: **BIOS/UEFI RTC wake** (emolevykohtainen; dokumentoi kloonausohjeeseen). Ei WoL/relettä edge-PC:lle oletuksena. |
| **YKV + diner-näyttö(t)** | Virta **OFF** päivän päätteeksi | **Katkaisija** (manuaalinen tai ajastettu pistorasia/rele) — erillään edge-PC:stä. Aamulla virta ON ennen/kanssa RTC-herätyksen. |
| **Päivän nollaus + tallennus** | Edellisen päivän CSV/JSON + `reset-day` | **Ensisijaisesti juuri ennen sammutusta** (timer-skripti: export → reset → `poweroff`). **Varalla heti bootissa**, jos edellinen päivä jäi nollaamatta (esim. kova katkaisu / timer ohitettu). `export_before_reset` jo configissa. |

**Järjestys illalla (suositus):** (1) export + reset-day → (2) RTC arm → `poweroff` edge → (3) katkaisija OFF YKV + näytöt (henkilökunta tai ajastin ~minuutti softasammutuksen jälkeen).  
**Aamulla:** katkaisija ON → RTC herättää edgen → `havikki-ykv-link` + kiosk-app + Chromium (+ `havikki-day-boot-ensure` jos eilinen close jäi väliin).

**Skriptit:** `scripts/install-power-schedule.sh`, `havikki-day-close.sh`, `havikki-day-boot-ensure.sh`, `havikki-rtc-wake.sh` — ohje [`docs/power-schedule.md`](docs/power-schedule.md).

**Ei oletuksena:** edge-PC samalla releellä kuin YKV (RTC-wake vaatii PC:n ACC standby / G3-tilan emolevyn mukaan — testaa kohdekoneella).

Backlog: Adminin kellonajat UI (valinnainen); skriptit **tehty** (M-A12).

**Back to live YKV** (from mock):
```bash
sudo rm -f /etc/systemd/system/havikki-kiosk-app.service.d/mock.conf
sudo mv /etc/systemd/system/havikki-kiosk-app.service.bak-live \
        /etc/systemd/system/havikki-kiosk-app.service   # if backup exists
# Prefer 0.0.0.0 for LAN admin: sed or re-run install-kiosk-autostart.sh
sudo systemctl unmask --runtime havikki-ykv-link.service 2>/dev/null || true
sudo systemctl daemon-reload
sudo systemctl enable --now havikki-ykv-link.service
sudo systemctl restart havikki-kiosk-app.service
# Manual without systemd app: ./scripts/start-kiosk.sh --live
```

## Prod (later)
Same offline LAN model (edge + switch + YKV + admin PC). Hardware may be miniPC or Raspberry Pi 5.

**Hand-off from lab:** after YKV sign-off and final UI → reproduce via repo scripts on clean Ubuntu, then optionally package **Clonezilla image and/or custom ISO → bootable USB** ([`docs/roadmap-deployment.md`](docs/roadmap-deployment.md) §4).

## Thresholds
- Settle ~10 s (live) / 2 s (mock demo default)
- Smile &lt; 300 g, frown ≥ 300 g **per addition** (not total bin weight)
- After feedback: baseline = current weight; next `start_delta_g` rise starts a new event without emptying
- Near-empty (net ≤ `empty_g`, default 20 g) sustained **`empty_away_s`** (default 20 s) → phase `away` (tyhjennys); no waste events
- Bin returned (weight rises from away floor by ≥ `start_delta_g`) → **auto-tare** (SAD soft-tare offset + KCP `T` / mock tare); baseline 0; IDLE — day kg unchanged
- Manual **Taara** / scale zero: empty bin (not waste). On SAD path, tare is a **software offset** (`_sad_tare_g`); KCP `T` alone does not change SAD grams
- UI live-paino = `live_addition_g` (delta since baseline); day kg = SQLite day totals
- **Nollaa** → `POST /api/reset-day` clears today's events (bottom counters); **Taara** → SAD soft-tare (+ KCP `T`)
- Calendar day change → auto-refresh day stats on `/api/state`
- Env (boot override): `HAVIKKI_EMPTY_AWAY_S`, `HAVIKKI_EMPTY_G`, `HAVIKKI_THRESHOLD_G`, `HAVIKKI_SETTLE_S`
- Persistent admin config: `data/config.json` via `GET/POST /api/config`; admin UI on edge localhost or LAN `http://<edge-ip>:8080/admin`
- Day export: `GET /api/export/day.csv|.json`; `POST /api/reset-day` exports to `data/exports/` when `export_before_reset`
- Pre-filled bin: `prefill_waste_g` and/or `POST /api/set-baseline` (tare does not clear day kg)
