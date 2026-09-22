# YKV-02 load-cell wiring

## Pad order (PCB, left → right)

Typical marking:

| Pad | Notes |
|-----|--------|
| **E+** | Excitation + |
| **S+** | Sense / alternate signal (see ohje) |
| **OUT+** | **Lab platform signal +** (per device ohje — verified working) |
| **OUT−** | **Lab platform signal −** (per device ohje — verified working) |
| **S−** | Sense / alternate signal (see ohje) |
| **E−** | Excitation − |
| **Shield** | Cable shield |

Strain relief for load-cell cable: typically **4–8 mm**.

## Lab rule (Hävikkivaaka)

Successful empty↔50 kg `SAD` tracking was done with the load-cell **signal pair on `OUT+` / `OUT−`**, following the **unit’s own wiring ohje** — not a generic “always S+/S−” rule from other KERN PDFs.

Always prefer:

1. Sticker / printed ohje on **this** YKV + platform cable  
2. Empiric check: `SAD` must change when mass is added  
3. Generic manuals last

## 4-wire vs 6-wire

Follow the platform cable colour chart shipped with the cell. If the ohje shows only four conductors into OUT± and E±, that is enough for that unit.

## Compatibility

- YKV-02: analog strain-gauge platforms meeting transmitter specs.
- Cell body barcode is often a **serial**, not a model — use the platform type plate for Max kg.
- App weight path: **SAD** + `data/ykv_sad_cal.json` (KCP `SI` kg-cal may fail with `E0012` even when wiring is correct).

## Known failure modes

1. Open / swapped excitation → `SAD` flat.
2. Assuming S± when the ohje says OUT± (or the reverse) → no or wrong span.
3. KCP `JAG*` → `JAS I E0012` despite good `SAD` → use SAD cal, do not force SI.
4. Fake second `JALL` point without weight → corrupt `SI` span.
