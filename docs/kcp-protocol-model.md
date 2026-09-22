# KCP protocol model (hävikkivaaka)

Source: KERN Communications Protocol (KCP) Reference Manual  
File: `KCP-ZB-e-v1.3.8.pdf` · Manual 1.3.8 (2019-04) · Protocol family ~1.1.2  
Device target: **YKV-02** over **Ethernet TCP port 23** (also USB/RS-232 possible).

This is an **application model** for our software — not a verbatim copy of the manual.

---

## 1. Transport

| Interface | Defaults |
|-----------|----------|
| RS-232 / RS-485 | 9600 8N1 |
| Ethernet (YKV-02) | TCP **port 23**, ASCII KCP |
| USB | Virtual serial / host link (YKV manual); good fallback at dealer |

Framing: every command ends with **CR LF** (`\r\n`).  
Encoding: ASCII. **Case-sensitive**; send commands in **uppercase**.

---

## 2. Message shape

```
Command:  <CMD>[ <arg1> <arg2> ...]<\r\n>
Response: <CMD> <status>[ <data>...]\r\n
     or:  ES\r\n          # syntax / unknown command
```

### Status letters (common)

| Code | Meaning |
|------|---------|
| `A` | Accepted / acknowledge |
| `L` | Logical error / bad parameter |
| `I` | Internal / busy / timeout / not executable now |
| `S` | Stable (weight replies) |
| `D` | Dynamic / unstable (weight replies) |
| `+` / `-` | Overload / underload |
| `ES` | Erroneous syntax / unknown command |

**Reliability rule:** wait for a response before sending the next command (queue overflow / missed cmds on some devices).

Cancel continuous streams / reset: command `@` (and hardware break).  
`SIR` is cancelled by `S`, `SI`, or `@`.

---

## 3. Weight value format

For `S` / `SI` / `SIR` replies:

- Weight is a **right-aligned 10-character** field (incl. decimal point).
- Decimal separator: **`.`** (point).
- Minus sign is part of the numeric field (no space between `-` and digits).
- Unit follows (e.g. `g`, `kg`).

Example lines (spaces matter in the 10-char field):

```
S S     100.00 g
S D     129.07 g
S S    -100.00 g
```

Parser should: split on whitespace carefully, or regex e.g.  
`^(S|SI|SX)\s+([SDI+\-]|[A-Z]+)\s+([-\d. ]+)\s+(\S+)`  
then `float(weight.strip())`.

---

## 4. Commands we need (Level 0 — Weighing Basic)

| CMD | Use in our app | Behaviour |
|-----|----------------|-----------|
| `SI` | Live display / stability detect | Immediate weight; `S` or `D` |
| `SIR` | Optional continuous stream (~15 Hz) | Repeat until stopped by `S`/`SI`/`@`; optional interval ms |
| `S` | Confirm stable reading | Waits until stable or timeout → `S I` |
| `T` | Tare empty bin | After stability; `T A` / `T I` / `T +`… |
| `TI` | Tare immediately | If needed |
| `Z` | Zero after stability | Daily zero |
| `ZI` | Zero immediately | If needed |
| `U` / `U g` | Ensure grams | Query/set unit |
| `I1` | Diagnostics | KCP version on device |
| `JNEA` / `JNEK` / `JNEG` | Ethernet IP setup | Must set all three in sequence (except DHCP) |

### Not required for MVP
Peak modes (`SIM`), piece counting, axis, memory dump (`SMEM`), adjustment (Level 2), digital-platform `SJ`/`SJR` (optional later).

---

## 5. Application state machine (mapping)

```
[BOOT]
  connect TCP host:23
  optional: I1, U g
  Z or T empty bin  →  [IDLE]

[IDLE]  (bin empty / tared)
  poll SI (or SIR)
  when weight rises & stays delta > threshold  →  [SETTLING]

[SETTLING]
  wait ~10 s with SI samples “stable enough”
  classify: <300 g smile / ≥300 g frown
  log event  →  [HOLD]

[HOLD]
  net ≤ empty_g for empty_away_s → [AWAY] (tyhjennys; no waste event)
  else next addition delta → [SETTLING]

[AWAY]
  bin returned (weight rises from away floor) → auto T (tare empty bin) → [IDLE]
```

Continuous `SIR` simplifies polling but requires careful cancel (`@` or `SI`) before `T`/`Z`.

---

## 6. Network commands (Ethernet)

| CMD | Role |
|-----|------|
| `JNEA` | Query/set IP; `JNEA 0.0.0.0` = DHCP |
| `JNEK` | Subnet mask |
| `JNEG` | Gateway |

Static config requires **JNEA → JNEK → JNEG** in sequence.  
YKV factory Ethernet: **DHCP client** (needs a DHCP server on the link).

WiFi AP config path (YKV manual): AP `AI-Thinker_…`, web UI `192.168.4.1`.

---

## 7. Minimal wire examples

```
→ SI\r\n
← S D     129.07 g\r\n

→ S\r\n
← S S     130.00 g\r\n

→ T\r\n
← T A\r\n

→ Z\r\n
← Z A\r\n

→ @\r\n
```

TCP smoke test from Linux:

```bash
nc -v 192.168.50.11 23
# type: SI   then Enter (ensure CR LF — some nc need printf)
printf 'SI\r\n' | nc -v 192.168.50.11 23
```

---

## 8. Python model sketch

```python
# Conceptual — see tools/kcp_client.py
class KcpClient:
    def send(self, cmd: str) -> str: ...
    def si(self) -> tuple[str, float, str]:  # status, value, unit
    def tare(self) -> None: ...
    def zero(self) -> None: ...
    def stop_stream(self) -> None:  # send "@" or "SI"
```

---

## 9. Risks / dealer notes

1. **Direct Ethernet without DHCP:** YKV may get no IP → use laptop DHCP (`dnsmasq`), or pre-set static IPs, or use reseller LAN.
2. **USB first:** fastest smoke test if Ethernet addressing is unclear.
3. **Wrong terminator:** LF-only often fails; always `\r\n`.
4. **Case:** `si` ≠ `SI`.
