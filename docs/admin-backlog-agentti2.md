# Admin-backlog — Agentti 2

**Rooli:** Admin-dashboard ja konfigurointi (kirjoitus). Kiosk vain lukee configia `/api/state`-snapshotista; kirjoitus vain suojattuihin tare/reset -toimintoihin.  
**Peruste:** `docs/kilpailija-ominaisuusanalyysi.md` §4 + `docs/kiosk-kilpailija-esitys.md` §3 + käyttäjän päätökset (S1/S2/S4, M4 dual-scale).  
**Päivitetty:** 2026-09-10  
**Koodi:** `app/static/admin.html`, `app/config.py`, `app/server.py`, `app/storage.py`  
**Käyttö:** Admin-PC kytkimen kautta → `http://<edge-ip>:8080/admin` (HTTP bind `0.0.0.0`). Ei vaadi toista HDMI:tä edge-koneessa. Katso `system_architecture.md` → *Deployment*.  
**Ajoitus:** lopulliset admin-UX-muutokset **YKV-toimintatestin jälkeen** (Lenovo = testikokoonpano). Kloonaus/ISO: `docs/roadmap-deployment.md`.

---

## 1. Jo toteutettu adminissa

Checklist nykyisestä lab-/dealer-administa (`/admin`):

- [x] **Admin-sivu** — `GET /admin` / `admin.html` (linkki kioskista)
- [x] **Laite-/piste-status (1 vaaka)** — `GET /api/health`: connected, mode (live/mock), phase, error, last_poll_ok_at, last_event_g, site_id, theme; pollaus ~3 s
- [x] **Päivän yhteenveto** — kpl, kg, avg g, max g, hymy %, suru; päiväsuodatin `YYYY-MM-DD`
- [x] **Tapahtumalista** — `GET /api/events?day=&limit=&offset=` (ts, g, feedback)
- [x] **Kynnysten / settle / empty -parametrien UI** — kirjoitus `POST /api/config` → `data/config.json`, hot-reload
- [x] **Binääripalaute-tekstit (S1 osittain)** — `feedback_smile_text`, `feedback_frown_text` muokattavissa administa
- [x] **Teema dark/light (S4)** — `theme` select; riittää toistaiseksi (ei väripickereitä)
- [x] **site_id** — teksti kentässä (yksittäisen pisteen tunniste; ei monipiste-aggregaatiota)
- [x] **CO₂-kerroin configissa** — `co2_factor_kg_per_kg`; JSON-viennissä `co2_kg` lasketaan
- [x] **Päivän CSV-vienti** — lataus `GET /api/export/day.csv` + levylle `POST /api/export/day` (CSV+JSON → `data/exports/`)
- [x] **Päivän JSON-vienti** — `GET /api/export/day.json`
- [x] **Nollaa päivä** — `POST /api/reset-day` (+ valinnainen vienti `export_before_reset`)
- [x] **Aseta baseline** — `POST /api/set-baseline` (esitäytetty astia)
- [x] **Tyhjän astian / esitäytön / settle-parametrit** — empty_bin_g, toleranssi, prefill_waste_g, empty_g, empty_away_s, start_delta_g, feedback_show_s

**Ei vielä adminissa (vaikka kilpailija-Must mainitsee):** viikko-/kuukausinäkymä, trendikaaviot, jakso-CSV, kolmiportaiset kynnykset, per-scale health, auth, hälytykset, PDF, kategoriat.

---

## 2. Puuttuu — Must / Should / Could

Kartta: Agentti 3 §3 (admin omistaa) + kilpailija-analyysi §4 Must adminille + kiosk-planin config-omistukset (S1/S2/S4, M4).

### Must

| # | Ominaisuus | Lähde | Nykytila | Agentti 2 -työ |
|---|------------|-------|----------|----------------|
| M-A1 | **Viikko-/kuukausinäkymä** (kg, kpl, avg, smile%/frown%) | Kilpailija Must 1; Agent 3: historiaraportit | Vain yksi päivä | `GET /api/stats/daily?from&to` + admin-aggregaatit |
| M-A2 | **Tapahtumalista + päiväsuodatus** | Kilpailija Must 2; Agent 3: event list | **Tehty** | Pidä; laajenna tarvittaessa `from`/`to` + sivutus UI |
| M-A3 | **CSV-vienti (päivä / jakso)** | Kilpailija Must 3; Agent 3: CSV/PDF | Päivä OK; **ei jaksoa** | `GET /api/export.csv?from&to` (+ UI) |
| M-A4 | **Kynnysten muokkaus UI** | Kilpailija Must 4; Agent 3 | Yksi `threshold_g` | Säilytä; laajenna → **S2 kolmiportaisuus** (alla) |
| M-A5 | **Device health -dashboard** | Kilpailija Must 5; Agent 3; M4 dual-scale | Yksi `connected` | Per-scale status (`scale_id` A/B): connected / last_poll / error |
| M-A6 | **S2: kolmiportaiset kynnykset** | Kiosk-plan S2; admin kirjoittaa | Ei (`smile`\|`frown` vain) | Config: `threshold_ok_g`, `threshold_frown_g` (+ `feedback_ok_text`); kiosk lukee staten kautta |
| M-A7 | **S1: viestiprofiilit / ympäristösävyt** | Kiosk-plan S1 | Vain vapaat smile/frown -tekstit | Profiilit `koulu`\|`buffet`\|`hotelli` *tai* selkeät per-ympäristö -tekstit; admin valitsee |

### Should

| # | Ominaisuus | Lähde | Nykytila | Agentti 2 -työ |
|---|------------|-------|----------|----------------|
| S-A1 | **Monipiste (site_id / scale_id)** | Kilpailija Should 6; Agent 3 | `site_id` string | Eventeihin `site_id`/`device_id`; admin suodatus; ei vielä ketju-UI |
| S-A2 | **Käyttäjät / roolit** (admin vs katselija) | Kilpailija Should 7; Agent 3 | Ei auth | Yksinkertainen PIN/salasana admin-kirjoitukseen; kiosk tare/reset erikseen suojattu |
| S-A3 | **Trendikaaviot** 7/30 pv | Kilpailija Should 8; Agent 3: trendit | Ei | Chart päiväaggregaateista (smile/frown/ok -jakauma) |
| S-A4 | **CO₂ / ESG näkyväksi** | Kilpailija Should 9; Agent 3 | Kerroin + JSON-kenttä | Näytä kg CO₂ päivä-/jaksonäkymässä; kerroin jo UI:ssa |
| S-A5 | **Hälytykset / briefingit** | Kilpailija Should 10; Agent 3 | Ei | Offline > N min; päivän kg > tavoite → webhook/sähköposti |
| S-A6 | **Locale config** (fi/en/sv) | Kiosk M5; admin kirjoittaa | Ei | `locale` configissa; kiosk lukee |

### Could

| # | Ominaisuus | Lähde | Nykytila |
|---|------------|-------|----------|
| C-A1 | Hävikkikategoriat (plate default) | Agent 3; Kilpailija Could 11 | Ei |
| C-A2 | Toimipistevertailu | Agent 3; Kilpailija Could 12 | Ei |
| C-A3 | Ruokalista / menu_tag / menekkiarvio | Agent 3; Kilpailija Could 13 | Ei |
| C-A4 | PDF-raportti johdolle | Agent 3; Kilpailija Could 14 | Ei |
| C-A5 | API-avain ulkoiseen BI:hin | Kilpailija Could 15 | Ei |
| C-A6 | Väripickerit / brändivärit | Käyttäjä: S4 later | Ei — dark/light riittää |

---

## 3. API-sopimus kioskin kanssa

**Periaate:** Admin kirjoittaa configin ja lukee raportteja. Kiosk lukee runtime-staten; kirjoittaa vain suojattuihin huolto-endpointteihin. Ei kilpailevia kirjoittajia samoihin kenttiin.

| Endpoint | Kuluttaja | Oikeudet | Huom |
|----------|-----------|----------|------|
| `GET /api/state` | **Kiosk** (pääasiallinen) | luku | Snapshot + `config`-osajoukko (thresholdit, tekstit, theme, site_id, …) |
| `GET /api/config` | Admin (+ työkalut) | luku | Koko `AppConfig` |
| `POST /api/config` | **Vain admin** | kirjoitus | Validointi `config.py`; hot-reload; kiosk näkee seuraavassa state-pollissa |
| `GET /api/health` | Admin | luku | Device health; laajenna → per-scale |
| `GET /api/events?...` | Admin | luku | Kiosk ei tarvitse (käyttää staten day-stats) |
| `GET /api/stats/daily?...` | Admin *(tulossa)* | luku | Aggregaatit |
| `GET /api/export/...` / `POST /api/export/day` | Admin | luku/vienti | Kiosk ei vie |
| `POST /api/tare`, `/api/reset-day`, `/api/set-baseline` | Kiosk (suojattu) / admin-työkalut | kirjoitus | Päivän data / vaaka — ei config-kenttiä |
| `POST /api/demo/*` | Mock-kiosk | kirjoitus | Vain mock |

**Konfliktien välttäminen**

- Kynnys-/viesti-/teema-arvot: **yksi lähde** `data/config.json` via `POST /api/config`. Kiosk ei tallenna näitä.
- Tapahtumat: vain tilakone → `storage.add_event`. Admin ei luo fake-eventejä (paitsi ehkä tulevissa testeissä).
- `reset-day`: kiosk staff-UI (PIN) **tai** admin; sama endpoint — dokumentoi, ettei kaksoisnollaus yllätä.
- Uudet S2-kentät (`threshold_ok_g`, `threshold_frown_g`, `feedback_ok_text`): admin kirjoittaa → sisällytetään `snapshot()["config"]` → kiosk/tilakone lukee.

---

## 4. Ei tehdä

| Aihe | Syy |
|------|-----|
| **AI-kamera / Throw & Go -keittiöpino** | Eri use case (Winnow/Orbisk/KITRO); ei prioriteetti lautashävikkikioskille |
| **Avaimet käteen -asennuspalvelu** | Liiketoiminta / Serve-tyyppinen palvelu, ei admin-UI |
| **Väripickerit / monimutkainen teemoitus** | Käyttäjä: S4 dark/light riittää nyt |
| **Kioskin kosketuslayout, PIN-huoltovalikko, offline-grace UI** | Agentti 3 — admin vain toimittaa configin (locale, tekstit, kynnykset) |

---

## 5. Seuraava sprintti

Konkreettiset tehtävät järjestyksessä (5–8 kpl). Pieniä API/config-laajennuksia ensin, sitten admin-UI.

1. **S2 config-malli** — Lisää `threshold_ok_g`, `threshold_frown_g`, `feedback_ok_text` (`config.py` + validointi); säilytä `threshold_g` siirtymäajan tai mapataan frown-kynnykseen; altista `GET/POST /api/config` + `snapshot()["config"]`.
2. **Admin UI: kolmiportaiset kynnykset + ok-teksti** — Korvaa/laajenna yksi “Hymy/suru-kynnys” -kenttä kahdella kynnyksellä + ok-viestillä; dokumentoi kioskille (Agentti 3 toteuttaa tilakoneen `ok`-feedbackin).
3. **S1 viestiprofiili** — `message_profile` (koulu/buffet/hotelli) *tai* selkeä ohje + esitäytöt; admin valitsee → tekstit päivittyvät (override edelleen mahdollista).
4. **Jaksoaggregaatit API** — `GET /api/stats/daily?from=&to=` (kg, kpl, avg, smile/ok/frown); admin: viikko-/kuukausiyhteenveto taulukkona (kaavio voi olla seuraava).
5. **CSV-vienti jaksolle** — `from`/`to` query; admin-painike “Vie jakso”.
6. **Device health per-scale (M4)** — Health-payloadiin `scales[]` (`scale_id`, connected, last_poll, error); admin-ruudukko “vaaka A/B”; yksivaaka-labissa yksi rivi (taaksepäin yhteensopiva).
7. **CO₂ päivänäkymässä** — Laske `total_kg × co2_factor` dayStats-korttiin (kerroin jo configissa).
8. **(Jos aikaa) Locale-kenttä** — `locale: fi|en|sv` config + admin select; kiosk lukee myöhemmin (M5).

**Sprintin ulkopuolelle (seuraava jono):** auth/roolit, trendikaaviot, hälytykset, event `site_id`/`device_id` -skeema, PDF, kategoriat.

---

*Backlog only. Ei suuria feature-toteutuksia tässä dokumentissa.*
