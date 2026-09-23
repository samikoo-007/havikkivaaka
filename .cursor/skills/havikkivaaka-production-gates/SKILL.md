---
name: havikkivaaka-production-gates
description: >-
  Gate Hävikkivaaka before any non-lab handoff: path traversal on /static/,
  open admin on 0.0.0.0, DHCP on the YKV NIC, blocking multi-scale poll,
  SQLite power loss, SAD vs factory SI, settle_s at a lunch line. Use when
  reviewing production readiness, security, deploy, cloning, admin auth, or
  when an agent lists showstoppers for this repo. Also use when adding HTTP
  static serving, LAN admin APIs, dnsmasq, or a second scale poll.
---

# Production gates (isolated appliance)

Hävikkivaaka is an **offline isolated system** (own switch/cable only). Never claim it is safe on a school/office LAN or the internet. See `system_architecture.md` → *Network model*.

Lenovo remains a **testikokoonpano**. Verify claims in code. Run: `python3 tools/test_security_gates.py`.

## Threat model

| Audience | Assumption |
|----------|------------|
| Isolated switch | Admin PC + edge + YKV only. PIN still required after install. |
| Site / guest Wi-Fi | **Out of scope.** Do not deploy there. |

`0.0.0.0:8080` is intentional for the isolated admin PC. Do not “fix” by binding `127.0.0.1` only.

## Implemented (keep intact)

1. **`/static/` containment** — `safe_static_file()`; only under `app/static`.
2. **Admin PIN** — `HAVIKKI_ADMIN_PIN` in `/etc/havikkivaaka/env` (install generates). Header `X-Havikki-Pin`. HTML `/admin` is a public shell; APIs gated. Kiosk `GET /api/state` + `GET /api/health` stay open.
3. **Body cap** — 64 KiB JSON POSTs.
4. **DHCP preflight** — `enable-ykv-link.sh` refuses default-route iface (`HAVIKKI_ALLOW_DHCP_ON_DEFAULTED_IFACE=1` lab escape only).
5. **SQLite WAL** + `synchronous=FULL`.
6. **Poll** — KCP timeout 0.4 s; skip dead slot ~5 s.
7. **Per-slot SAD** — `ykv_sad_cal_{a,b,c}.json` else shared file else `SI`.

## Still deferred (do not turn into a rewrite)

| Topic | Status |
|-------|--------|
| Replace `http.server` | Not required on isolated LAN; keep stdlib. |
| TLS/HTTPS | Not needed without uplink. |
| `settle_s` default 10 s | Admin-tunable; change only after a timed line trial. |
| Off-host backup | Day exports on local disk; USB copy is ops, not code. |

## Agent do / don't

**Do**

- Keep path checks, PIN header (not cookie), DHCP refusal, WAL.
- Default install user to `SUDO_USER`; iface auto-detect or `HAVIKKI_IFACE`.
- Document isolated LAN in any deploy/handoff text.

**Don't**

- Remove PIN “for convenience” on a handoff image.
- Add cookie sessions without the header PIN (CSRF).
- Start dnsmasq on an iface that is the site default route.
- Copy lab `ykv_sad_cal.json` onto a new platform.

## Tests that must stay green

`python3 tools/test_security_gates.py` — path 404, PIN 401, kiosk state 200, body 413, settle merge / feedback behaviour.
