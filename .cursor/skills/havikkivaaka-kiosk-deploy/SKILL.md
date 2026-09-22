---
name: havikkivaaka-kiosk-deploy
description: >-
  Deploy and replicate the Hävikkivaaka live kiosk on any (X)Ubuntu host (bootstrap,
  YKV Ethernet DHCP, SAD cal, systemd Chromium kiosk). Use when the user mentions
  monistaa kiosk, puhdas Ubuntu, Xubuntu asennus, kloonaus, install-kiosk,
  bootstrap-xubuntu, production deploy, uusi kone, or shipping the working Lenovo
  stack to another PC.
---

# Hävikkivaaka kiosk deploy (any Xubuntu)

**Proven (2026-09-22 lab):** Lenovo live kiosk + YKV Ethernet + `SAD` weight cal works end-to-end. Replicate that stack on a **clean (X)Ubuntu** host with repo scripts — do not rely on Lenovo-only manual state.

Hardware/cal details: [`ykv-commissioning`](../ykv-commissioning/SKILL.md).  
Day-to-day lab (Mac cable, mock): [`havikkivaaka-lab`](../havikkivaaka-lab/SKILL.md).

## Target stack (golden)

| Layer | What |
|-------|------|
| Host | Ubuntu/Xubuntu Desktop LTS (lab may be newer) |
| Repo | `~/havikkivaaka` |
| Edge LAN | `192.168.50.10/24` on YKV NIC (param via `HAVIKKI_*`) |
| YKV | DHCP → `192.168.50.11:23` KCP |
| Weight | **`data/ykv_sad_cal.json`** + KCP `SAD` (not raw `SI` kg) |
| App | `python3 -m app.server --host 192.168.50.11 --port 23 --http-host 0.0.0.0 --http-port 8080` |
| UI | Chromium kiosk `http://127.0.0.1:8080/` ; admin `http://<edge-ip>:8080/admin` |
| Boot | `havikki-ykv-link` + `havikki-kiosk-app` + LightDM autologin |

## Deploy checklist (new machine)

```
Deploy progress:
- [ ] 1. Install (X)Ubuntu Desktop; create user (e.g. sami) with sudo
- [ ] 2. Clone/copy repo → ~/havikkivaaka
- [ ] 3. sudo ./scripts/bootstrap-xubuntu.sh
- [ ] 4. Set iface/IP env if not enp1s0 / .10 (see Env)
- [ ] 5. sudo ./scripts/install-kiosk-autostart.sh   # live units, no mock.conf
- [ ] 6. Commission YKV + SAD cal (ykv-commissioning skill) → data/ykv_sad_cal.json on host
- [ ] 7. CAT6 edge ↔ YKV; sudo ./scripts/enable-ykv-link.sh (or reboot)
- [ ] 8. Verify: ping .11, connected=true, weight moves with load
- [ ] 9. Reboot once; confirm kiosk autostarts
```

## Commands (copy)

```bash
cd ~/havikkivaaka
sudo ./scripts/bootstrap-xubuntu.sh
# Optional overrides before install:
#   export HAVIKKI_IFACE=enp1s0 HAVIKKI_USER="$USER"
sudo ./scripts/install-kiosk-autostart.sh

# After cal file is present and cable to YKV:
sudo ./scripts/enable-ykv-link.sh
sudo systemctl restart havikki-kiosk-app
curl -s http://127.0.0.1:8080/api/state   # mode=live, connected, weight_g / bin_weight_g

# From admin PC on same LAN (switch or second NIC):
#   http://192.168.50.10:8080/admin
```

### Env knobs

| Variable | Role |
|----------|------|
| `HAVIKKI_IFACE` | Ethernet to YKV (default often `enp1s0`) |
| `HAVIKKI_HOST` | YKV IP (default `192.168.50.11`) |
| `HAVIKKI_HTTP_HOST` | Bind (`0.0.0.0` for LAN admin) |
| `HAVIKKI_HTTP_PORT` | Default `8080` |
| `HAVIKKI_USER` | Service/autologin user |
| `HAVIKKI_MOCK` | Force mock (UI-only; not for dealer live) |

### Mock vs live

| Goal | Action |
|------|--------|
| Live YKV (default dealer) | No `mock.conf`; `havikki-ykv-link` + `havikki-kiosk-app` enabled |
| UI without scale | Drop-in mock + stop ykv-link (see lab skill) |

## SAD cal on the edge host

Kiosk reads weight from **SAD** when `data/ykv_sad_cal.json` exists. Capture on Mac USB or on the edge if serial/TCP available:

```bash
# Mac USB example (then rsync cal to edge):
python3 tools/ykv_sad_weight.py --capture empty --samples 8
# place ref weights (e.g. 10+20+20 kg)
python3 tools/ykv_sad_weight.py --capture ref --ref-kg 50 --samples 8

rsync -az data/ykv_sad_cal.json user@edge:~/havikkivaaka/data/
# restart havikki-kiosk-app on edge
```

Expect log: `weight source=SAD ...`. **Each physical YKV+platform pair** needs its own cal file.

## One-cable topologies (no switch)

| Cable | Purpose |
|-------|---------|
| Edge ↔ YKV | Live kiosk |
| Mac ↔ edge | SSH / rsync / admin |
| Mac ↔ YKV | Diagnostic only (commissioning) |

Not two Eth roles on one NIC at once. **Switch** preferred for Mac + edge + YKV together.

## Verify (pass criteria)

1. `ping 192.168.50.11` OK; TCP **23** open  
2. `api/state`: `"mode":"live"`, `"connected":true`  
3. Empty ≈ 0 g; known mass moves `bin_weight_g` / UI  
4. After reboot: kiosk fullscreen + same connected behavior  

## Agent do / don't

**Do**

- Prefer repo scripts over one-off systemd edits; mirror any host fix back into `scripts/`.  
- Ship `ykv_sad_cal.json` with the unit (or recapture on site).  
- Update `system_architecture.md` when adding services.  
- After deploy success, leave UI changes to the backlog below (phase 3).

**Don't**

- Claim deploy done on mock-only.  
- Rely on KCP `SI` kg without SAD cal on this hardware.  
- Hardcode Lenovo-only iface without `HAVIKKI_IFACE`.  
- Start Mac listen/DHCP unless user asked that turn.

## Next UI / product paths (phase 3 — not deploy blockers)

Confirmed direction after live single-scale works:

1. **Dual adjacent scales** — two YKV/platforms side by side; per-scale state, feedback, connection.  
2. **Footer stats** — same style as today’s day totals, aggregated (and/or per scale) from **both** scales’ events.  
3. **Admin UX** — improve reports, thresholds, health, dual-scale status; LAN via switch.  

More items may appear; treat the three above as fixed backlog. Details: `docs/admin-backlog-agentti2.md`, `docs/kiosk-kilpailija-esitys.md`, `docs/roadmap-deployment.md` §3.

## Related scripts

| Script | Role |
|--------|------|
| `scripts/bootstrap-xubuntu.sh` | Packages |
| `scripts/enable-ykv-link.sh` / `disable-ykv-link.sh` | DHCP `.11` + EEE |
| `scripts/havikki-boot-ykv.sh` | Boot oneshot |
| `scripts/install-kiosk-autostart.sh` | Systemd + LightDM + Chromium |
| `scripts/start-kiosk.sh` | Manual mock/live |
| `tools/ykv_sad_weight.py` | Capture/read SAD cal |

## Related docs

- [`docs/roadmap-deployment.md`](../../../docs/roadmap-deployment.md)  
- [`docs/dealer-day-checklist.md`](../../../docs/dealer-day-checklist.md)  
- [`system_architecture.md`](../../../system_architecture.md)  
