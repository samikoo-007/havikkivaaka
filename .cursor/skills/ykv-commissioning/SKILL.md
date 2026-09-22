---
name: ykv-commissioning
description: >-
  Commission and calibrate a new KERN YKV-02 + weighing platform for Hävikkivaaka
  (wiring, USB KCP probe, SAD weight cal, kiosk live). Use when the user mentions
  käyttöönotto, kalibrointi, uusi YKV, vaakayksikkö, kennokaapeli, SAD-cal,
  ykv_sad_cal, commission scale, or pairing a new transmitter + platform.
---

# YKV + platform commissioning

Handoff a **new** YKV-02 + analog platform so the kiosk reads real weight.  
Full host install / clone to any Xubuntu: [`havikkivaaka-kiosk-deploy`](../havikkivaaka-kiosk-deploy/SKILL.md).  
Lab networking (Mac cable, mock): [`havikkivaaka-lab`](../havikkivaaka-lab/SKILL.md).

## Hard facts (lab defaults)

| Item | Value |
|------|--------|
| Repo | `/Users/sami/Projects/havikkivaaka` |
| YKV USB | `/dev/cu.usbserial-*` (Mac FTDI), 9600 8N1 |
| YKV Ethernet | `192.168.50.11:23` KCP (after DHCP) |
| Weight source | **`SAD` + `data/ykv_sad_cal.json`** (preferred) |
| KCP `SI` kg | Often wrong / `JAS E0012` on this hardware — do **not** rely on SI alone |

YKV PCB pads **left → right:** `E+  S+  OUT+  OUT−  S−  E−  Shield`

**Lab / this platform (verified):** load-cell **signal pair on `OUT+` / `OUT−`** per the unit’s own wiring ohje. That is what worked when `SAD` tracked empty ↔ 50 kg.

Do **not** “fix” a working setup by moving SIG onto `S+/S−` unless the specific platform manual says so — pad names are easy to misread across KERN docs vs the sticker/ohje on the device.

## Checklist (copy and track)

```
Commission progress:
- [ ] 1. Physical: power, load-cell cable, USB (or Eth) to Mac/Lenovo
- [ ] 2. KCP alive: I2 / SAD responds
- [ ] 3. Signal proof: SAD empty vs known weight (Δ ≫ noise)
- [ ] 4. Write SAD cal: empty + ref weight → data/ykv_sad_cal.json
- [ ] 5. Verify: SAD-kg ≈ 0 empty, ≈ ref_kg with weights
- [ ] 6. Live kiosk: no mock; cal file present; restart app
- [ ] 7. Optional: Ethernet path on Lenovo (enable-ykv-link)
```

## 1. Physical

1. Platform load-cell cable → YKV per **device ohje** (lab success: signal on **`OUT+` / `OUT−`**; excitation as marked on the ohje).
2. Power YKV (USB-B is enough for USB KCP).
3. One topology at a time: Mac↔YKV USB **or** Lenovo↔YKV Eth (see lab skill).
4. Confirm display-unit test only if diagnosing the **platform**; for production the cell must terminate on YKV.

## 2. KCP alive (USB)

```bash
ls /dev/cu.usbserial*
python3 tools/ykv_signal_diag.py --label empty --samples 5
```

Expect `I2` like `YKV … kg`, and `SAD` numeric (not empty/timeout).

## 3. Signal proof (before writing cal)

| State | Expect |
|-------|--------|
| Empty | Stable `SAD` (lab cell ~8.46e6; **per-unit values differ**) |
| Known mass (e.g. 10+20+20 kg) | `SAD` jumps by **hundreds of thousands** of counts |

If `SAD` does not move → open circuit / wrong pair / no EXC; re-check against **device ohje** (lab: OUT± for signal).  
If `SAD` moves but `SI` stays 0 / nonsense → **expected**; use SAD cal below. Do not block on `JAG`/`JAS E0012`.

## 4. SAD calibration (per unit)

Weights: typically **10 + 20 + 20 kg**. Agent runs Terminal; user places weights when told.

```bash
# A) Platform empty
python3 tools/ykv_sad_weight.py --capture empty --samples 8

# B) After user places all ref weights and they settle
python3 tools/ykv_sad_weight.py --capture ref --ref-kg 50 --samples 8

# C) Readback
python3 tools/ykv_sad_weight.py --samples 5
```

File: `data/ykv_sad_cal.json` (`sad_empty`, `sad_at_ref`, `ref_kg`).  
**Each physical YKV+platform pair needs its own capture** (AD offsets differ).

Pass criteria:

| State | SAD-derived kg |
|-------|----------------|
| Empty | ≈ **0** (±0.5 kg) |
| Ref on pan | ≈ **ref_kg** (±1.5 kg) |

Optional KCP kg-cal (`tools/ykv_calibrate_usb.py`) is **not** required for kiosk if SAD cal passes. If tried: keep port open for whole sequence; never fake a second `JALL` point; prefer `--capacity-kg` = adj weight when only e.g. 50 kg available.

## 5. Kiosk live

App uses SAD automatically when `data/ykv_sad_cal.json` exists (`app/server.py` + `app/kcp.py`).

```bash
# Lenovo example after rsync (exclude overwriting cal unless intentional)
rsync -az --exclude '.git' --exclude 'logs/' --exclude '__pycache__' \
  ./ sami@192.168.50.10:~/havikkivaaka/
# Ensure data/ykv_sad_cal.json is on the edge host
sudo systemctl restart havikki-kiosk-app   # or ./scripts/start-kiosk.sh --live
curl -s http://192.168.50.10:8080/api/state   # connected, weight moves
```

## Agent do / don't

**Do**

- Drive commissioning with USB SAD first; treat `SI` as secondary.
- Tell the user **exactly when** to place / remove 10+20+20 kg.
- Capture empty only when `SAD` is at true unloaded level.
- Keep one cal file per deployed scale (or document unit id in the JSON `note`).
- Prefer the **sticker/ohje on the YKV** over generic “S+ = SIG” assumptions from other KERN manuals.

**Don't**

- Blindly move a working OUT± hookup to S± “because a PDF said so”.
- Claim end-to-end OK from display-unit-only tests.
- Complete `JALL B 200 kg` without a 200 kg weight (corrupts span).
- Start Mac Eth listen/DHCP unless the user asked this turn (lab skill).
- Commit secrets; cal JSON (AD counts) is OK to commit if no PII.

## Quick triage

| Symptom | Action |
|---------|--------|
| No `/dev/cu.usbserial*` | USB cable / FTDI; replug YKV |
| SAD flat empty↔load | Follow device ohje (lab: OUT± signal); check EXC and strain relief |
| SAD OK, SI 0 or wrong kg | Ignore SI; finish SAD cal |
| `JAS I E0012` | Skip KCP cal; use SAD |
| Empty SAD-kg ≠ 0 after cal | Re-`--capture empty` then `ref` |
| Kiosk weight wrong after swap | Recapture cal for that unit |

## Related

- Lab / Lenovo / listen: [`havikkivaaka-lab`](../havikkivaaka-lab/SKILL.md)
- Wiring detail: [`wiring.md`](wiring.md)
- Arch: [`system_architecture.md`](../../../system_architecture.md)
