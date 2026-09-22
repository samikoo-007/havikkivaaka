# havikkivaaka

Oma biojäte-/lautashävikkivaaka: **KERN-alusta + YKV-02 (KCP/Ethernet)** + kiosk-UI.

**Lab = testikokoonpano** (esim. edge-PC `192.168.50.10`): YKV-luvun ja softan validointi — ei tuotantoasennus. Vaiheet, puhdas Ubuntu -toisto ja ISO/USB-kloonaus: [`docs/roadmap-deployment.md`](docs/roadmap-deployment.md).

License: [MIT](LICENSE).

## Docs
- [`docs/roadmap-deployment.md`](docs/roadmap-deployment.md) — test → clean Ubuntu → final UI → clone/ISO/USB
- [`docs/kcp-protocol-model.md`](docs/kcp-protocol-model.md)
- [`docs/dealer-ethernet-prep.md`](docs/dealer-ethernet-prep.md)
- [`docs/mac-ykv-listen.md`](docs/mac-ykv-listen.md) — Mac-varakuuntelu (älä käynnistä ilman erillistä pyyntöä)
- [`docs/dealer-day-checklist.md`](docs/dealer-day-checklist.md)
- [`docs/kilpailija-ominaisuusanalyysi.md`](docs/kilpailija-ominaisuusanalyysi.md)
- [`docs/admin-backlog-agentti2.md`](docs/admin-backlog-agentti2.md)
- [`system_architecture.md`](system_architecture.md)
- SAD-kalibrointi: [`data/README.md`](data/README.md) + [`.cursor/skills/ykv-commissioning`](.cursor/skills/ykv-commissioning/SKILL.md)

## Quick start (Xubuntu)

Tavoite: samat komennot toimivat **puhtaalla Ubuntu-koneella** (kun labin YKV-polku on todettu). Lenovo on vain nykyinen testialusta.

```bash
# Paketit (kerran)
sudo ./scripts/bootstrap-xubuntu.sh

# Boot-kiosk (suositus Lenovolle): auto-login + live YKV + Chromium
sudo ./scripts/install-kiosk-autostart.sh
# Käynnistysvirta: network → havikki-ykv-link (EEE+DHCP) → havikki-kiosk-app → Chromium

# Mock-kiosk (kotona ilman YKV:tä / ilman boot-palveluita) — settle 2 s demoon
./scripts/start-kiosk.sh

# Manuaalinen live (jos boot-asennusta ei käytetä)
sudo ./scripts/enable-ykv-link.sh
./scripts/start-kiosk.sh --live
```

**Systemd mock (UI-työ Lenovolla, YKV pois):** drop-in `havikki-kiosk-app.service.d/mock.conf` + `sudo systemctl stop/disable havikki-ykv-link` + `sudo ./scripts/disable-ykv-link.sh`. Live takaisin: poista drop-in, palauta `.bak-live` tarvittaessa, `enable --now havikki-ykv-link`, `restart havikki-kiosk-app` — tai `./scripts/start-kiosk.sh --live`. Katso `system_architecture.md` → *Lab UI mode*.

Kiosk: http://127.0.0.1:8080/ — dual-scale display-only (A\|B); mockissa esittelynapit A/B. Taara / Nollaa / asetukset → `/admin`.

## Admin

Admin ajetaan **kytkimen kautta** erilliseltä koneelta (offline LAN). Edge-kone (kiosk) kuuntelee `0.0.0.0:8080`.

| Missä | URL |
|-------|-----|
| Edge-koneella (Lenovo / Pi) | http://127.0.0.1:8080/admin |
| Admin-PC samassa LAN:ssa (lab) | **http://192.168.50.10:8080/admin** |

Ei linkkiä kioskista — piilotettu URL. Override: `HAVIKKI_HTTP_HOST=127.0.0.1` jos haluat vain localhostin.

Asetukset tallentuvat `data/config.json` ja hot-reloadataan tallennuksessa (prosessia ei tarvitse käynnistää uudelleen).

| Asetus | Oletus | Kenttä |
|--------|--------|--------|
| Hymy/suru-kynnys | 300 g | `threshold_g` |
| Settle-aika | 10 s (mock-demo CLI: 2) | `settle_s` |
| Palautteen näyttö | 3.2 s | `feedback_show_s` |
| Tyhjän lukeman kynnys | 20 g | `empty_g` |
| Tyhjennysviive | 20 s | `empty_away_s` |
| Tyhjän astian paino | 0 (pois) | `empty_bin_g` + `empty_bin_tolerance_g` |
| Esitäytön baseline | 0 | `prefill_waste_g` + nappi „Aseta baseline” |
| Kioskin teema | `dark` | `theme` (`dark` \| `light`) |
| Vie ennen nollausta | true | `export_before_reset` |

**API:** `GET/POST /api/config`, `GET /api/export/day.csv`, `GET /api/export/day.json`, `POST /api/export/day` (tallennus `data/exports/`), `POST /api/reset-day` (vienti ennen tyhjennystä jos asetus päällä), `GET /api/health`, `GET /api/events?day=`.

**Vientisuositus:** CSV Exceliin + JSON API-/arkistokäyttöön (molemmat oletuksena).

### Agentti 3 — teema kioskissa

Kiosk lukee teeman `/api/state` (kentät `theme` ja `config.theme`) ja asettaa `document.documentElement` → `data-theme="light|dark"`. Adminin teema-toggle riittää; Agentti 3 ei tarvitse erillistä theme-API:a.

### Tyhjennys + auto-taara

Astia pois vaa'alta (netto ≈ 0) **yli 20 s** → vaihe `away` (tyhjennys). Astia takaisin → **auto-taara** (tyhjä astia = nolla); päivän kg ei kasva. Lisäykset jatkuvat kuten ennen.

| Asetus | Oletus | Merkitys |
|--------|--------|----------|
| `HAVIKKI_EMPTY_AWAY_S` / `--empty-away-s` | 20 | Sekunnit tyhjänä ennen tyhjennystä |
| `HAVIKKI_EMPTY_G` / `--empty-g` | 20 | Absoluuttinen netto ≤ tämä = pois vaa'alta |

```bash
# Nopea mock-testi (Mac / Lenovo)
python3 tools/test_empty_tare.py --empty-away-s 3

# Kiosk mock lyhyellä away-ajalla
python3 -m app.server --mock --settle-s 2 --empty-away-s 3 --http-port 8080
```

### Kiosk pois päältä

```bash
# Sulje Chromium-kiosk
pkill -f 'user-data-dir=/tmp/havikki-chrome-profile'

# Pysäytä backend (boot-asennus)
sudo systemctl stop havikki-kiosk-app

# Poista bootista (SSH säilyy)
sudo systemctl disable --now havikki-kiosk-app havikki-ykv-link
sudo rm -f /etc/lightdm/lightdm.conf.d/50-havikki-autologin.conf
rm -f ~/.config/autostart/havikki-kiosk.desktop
```

Logit: `~/havikkivaaka/logs/` ja `/tmp/havikki-*.log`. Labissa NOPASSWD-sudo on OK demoon — ei tuotantoverkkoon.

```bash
python3 tools/kcp_client.py --host 127.0.0.1 --port 2323 si   # erillinen mock
python3 tools/kcp_client.py --host 192.168.50.11 si            # YKV
# Mac-varakuuntelu (vain kun pyydetään): ./scripts/listen-ykv.sh --setup --once
```
