# havikkivaaka

Oma biojäte-/lautashävikkivaaka: **KERN-alusta + YKV-02 (KCP/Ethernet)** + kiosk-UI + Admin.

**Lab = testikokoonpano** (edge esim. `192.168.50.10`): YKV-luvun ja softan validointi. Tuotanto: sama softapino + hankintaohje.

| | Linkki |
|---|--------|
| **Kokoonpano + hankinta (KERN / Prodi)** | [`docs/kokoonpano-suositus.md`](docs/kokoonpano-suositus.md) |
| Ostopaikka | **[prodi.fi](https://prodi.fi/)** — [KERN](https://prodi.fi/tuotemerkki/kern/) |
| Arkkitehtuuri | [`system_architecture.md`](system_architecture.md) |
| Vaiheet / kloonaus | [`docs/roadmap-deployment.md`](docs/roadmap-deployment.md) |
| Päivärytmi (RTC + sammutus) | [`docs/power-schedule.md`](docs/power-schedule.md) |

License: [MIT](LICENSE).

## Mitä softa tukee

- Vaakakokoonpanot Adminissa: **A** · **A+B** · **A+C** · **A+B+C** · **C** (max 3 lähettäjää)
- Diner-kiosk: A full-width tai A\|B split; 3-portainen palaute; päivätilastot (lautas erillään keittiöstä)
- Admin: kynnykset, hostit, otsikko/sijainti, (i)-ohjeet, vienti, health
- Tuotanto: illan day-close + BIOS RTC -herätys; YKV/näyttö katkaisijalla

## Docs

- [`docs/kokoonpano-suositus.md`](docs/kokoonpano-suositus.md) — **hankinta + kokoonpano-suositus**
- [`docs/roadmap-deployment.md`](docs/roadmap-deployment.md) — test → clean Ubuntu → UI → clone/ISO
- [`docs/power-schedule.md`](docs/power-schedule.md) — poweroff / RTC wake
- [`docs/kcp-protocol-model.md`](docs/kcp-protocol-model.md)
- [`docs/dealer-ethernet-prep.md`](docs/dealer-ethernet-prep.md)
- [`docs/mac-ykv-listen.md`](docs/mac-ykv-listen.md) — Mac-varakuuntelu (älä käynnistä ilman erillistä pyyntöä)
- [`docs/dealer-day-checklist.md`](docs/dealer-day-checklist.md)
- [`docs/kilpailija-ominaisuusanalyysi.md`](docs/kilpailija-ominaisuusanalyysi.md)
- [`docs/admin-backlog-agentti2.md`](docs/admin-backlog-agentti2.md)
- [`docs/kiosk-kilpailija-esitys.md`](docs/kiosk-kilpailija-esitys.md)
- [`system_architecture.md`](system_architecture.md)
- SAD-kalibrointi: [`data/README.md`](data/README.md) + [`.cursor/skills/ykv-commissioning`](.cursor/skills/ykv-commissioning/SKILL.md)

## Quick start (Xubuntu)

```bash
sudo ./scripts/bootstrap-xubuntu.sh
sudo ./scripts/install-kiosk-autostart.sh
# Live: CAT6 → YKV, sudo ./scripts/enable-ykv-link.sh
# Tuotannon päivärytmi (BIOS RTC wake ensin):
# sudo ./scripts/install-power-schedule.sh

./scripts/start-kiosk.sh          # mock ilman YKV:tä
./scripts/start-kiosk.sh --live   # manuaalinen live
```

Kiosk: http://127.0.0.1:8080/ — Admin: http://127.0.0.1:8080/admin (LAN: `http://<edge-ip>:8080/admin`).

## Admin (lyhyt)

Asetukset → `data/config.json` (hot-reload). Layout, YKV-hostit, `kiosk_title`, `kiosk_location`, kynnykset, palauteviestit, teema.

| Asetus | Esimerkki |
|--------|-----------|
| `scale_layout` | `a` \| `a_b` \| `a_c` \| `a_b_c` \| `c` |
| `kiosk_title` | Hävikkivaaka |
| `kiosk_location` | Write location |
| `threshold_ok_g` / `threshold_g` | 200 / 300 g |
| `export_before_reset` | true |

**API:** `GET/POST /api/config`, `GET /api/export/day.csv|.json`, `POST /api/reset-day`, `GET /api/health`, `GET /api/events?day=`.

## Hankinta (KERN)

Vaa’at ja **YKV-02**-lähettimet: **[Prodi](https://prodi.fi/)** ([KERN](https://prodi.fi/tuotemerkki/kern/)). Yksityiskohdat ja esimerkkikokoonpanot: [`docs/kokoonpano-suositus.md`](docs/kokoonpano-suositus.md).

## Kiosk pois päältä

```bash
pkill -f 'user-data-dir=/tmp/havikki-chrome-profile'
sudo systemctl stop havikki-kiosk-app
sudo systemctl disable --now havikki-kiosk-app havikki-ykv-link
# Päivätimer (jos asennettu):
# sudo systemctl disable --now havikki-day-close.timer
```

Logit: `~/havikkivaaka/logs/`.
