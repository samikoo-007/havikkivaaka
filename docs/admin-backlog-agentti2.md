# Admin-backlog — Agentti 2

**Rooli:** Admin-dashboard ja konfigurointi (kirjoitus). Kiosk on **display-only** (`GET /api/state`); Taara / päivän nollaus / esittelymock / baseline → **vain Admin**.  
**Peruste:** `docs/kilpailija-ominaisuusanalyysi.md` §4 + `docs/kiosk-kilpailija-esitys.md` + UI-lock 2026-09-22 (dual-scale A\|B, 3-portainen palaute, min g) + **vaakamalli 1–3 (A/B/C) + kenttäohjeet 2026-09-22**.  
**Päivitetty:** 2026-09-22  
**Koodi:** `app/static/admin.html`, `app/config.py`, `app/server.py`, `app/storage.py`  
**Käyttö:** Admin-PC kytkimen kautta → `http://<edge-ip>:8080/admin` (HTTP bind `0.0.0.0`). Ei vaadi toista HDMI:tä edge-koneessa. Katso `system_architecture.md` → *Deployment*.  
**Ajoitus:** lopulliset admin-UX-muutokset **YKV-toimintatestin jälkeen** (Lenovo = testikokoonpano). Kloonaus/ISO: `docs/roadmap-deployment.md`.

### Lukittu: vaakojen määrä, nimet ja käyttötarkoitus (max 3)

Admin tukee **enintään kolmea vaakaa + lähetintä** (YKV). Slotit valitaan Adminissa; **sallitut kokoonpanot** (ei muita):

| Kokoonpano | Kiosk | Admin / data |
|------------|-------|--------------|
| **A** | Yksi paneeli, **koko näytön leveys** | Lautashävikki |
| **A+B** | Peilattu split vasen\|oikea | Lautashävikki yhteensä |
| **A+C** | A koko leveys (C ei kioskissa) | Lautas (A) + tuotanto (C) erillään |
| **A+B+C** | Kuten A+B (C ei kioskissa) | Lautas (A+B) + tuotanto (C) erillään |
| **C** | **Ei kiosk-tilaa ollenkaan** (ei Chromium-diner-UI:ta) | Vain tuotantohävikki |

**Ei sallittu (v1):** vain B, vain B+C. (Skeema laajennettavissa myöhemmin.)

| Slot | Kiinteä Admin-nimi | Käyttötarkoitus |
|------|--------------------|-----------------|
| **A** | Vasen lohko | Näytön vasen (tai koko leveys jos A yksin) — ruokailijapalaute |
| **B** | Oikea lohko | Näytön oikea — ruokailijapalaute |
| **C** | Keittiön hävikki | Tuotantohävikki: **vain tietojen keruu**, ei hymy/ok/suru -palautetta |

**C-logiikka:** astian tyhjennys sama periaate kuin A/B (empty-bin / auto-taara). Päätavoite: **päiväkohtainen kokonaishävikki** (g/kg). Tilastot **aina erillään** A+B:stä (ei summata diner-kg:hen).

**Lähetinosoitteet:** A/B/C host (ja portti tarvittaessa) muokattavissa **Admin UI:sta** (ei vain env). Env voi olla oletus/bootstrap.

**Skaalaus:** nyt max 3; config-/event-skeema suunnitellaan niin että slotteja voi lisätä myöhemmin.

### Lukittu: päivittäinen virta (M-A12)

| Osa | Päätös |
|-----|--------|
| Edge käynnistys | **BIOS RTC wake** (esim. 08:00) |
| Edge sammutus | Softa-timer → export/reset → `poweroff` (esim. 18:00) |
| YKV + näytöt | Virta **OFF katkaisijalla** (ei edge-PC:n relettä oletuksena) |
| Päivän tallennus/nollaus | **Ennen sammutusta**; bootissa varmistus jos jäi tekemättä |

### Lukittu: Admin kenttäohjeet (i)

Jokaisen **muokattavan** Admin-kentän vieressä pieni **(i)**-kuvake. **Hover** riittää (lyhyt FI-tooltip: mitä arvon muuttaminen tekee). Ei erillistä ohjepaneelia v1:ssä.

---

## 1. Jo toteutettu adminissa

Checklist nykyisestä lab-/dealer-administa (`/admin`):

- [x] **Admin-sivu** — `GET /admin` / `admin.html` (linkki kioskista)
- [x] **Laite-/piste-status (1 vaaka)** — `GET /api/health`: connected, mode (live/mock), phase, error, last_poll_ok_at, last_event_g, site_id, theme; pollaus ~3 s
- [x] **Päivän yhteenveto** — kpl, kg, avg g, max g (→ **min g** dual-UI:ssa), hymy %, suru; päiväsuodatin `YYYY-MM-DD`
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

**Ei vielä adminissa:** viikko-/kuukausinäkymä, trendikaaviot, jakso-CSV, auth, hälytykset, PDF, kategoriat. (Vaakamalli A/A+B/A+C/A+B+C/C + (i)-hover **tehty**.)

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
| M-A5 | **Device health -dashboard (A/B/C)** | Kilpailija Must 5; vaakamalli 1–3 | Health osin A/B | Per-scale status (`scale_id` a\|b\|c): connected / last_poll / error / nimi / käyttötarkoitus; kiosk **ei** näytä mode/conn |
| M-A6 | **S2: kolmiportaiset kynnykset** — **hyväksytty** | Kiosk S2 lukittu 2026-09-22 | Osittain configissa | UI + tilakone: `threshold_ok_g` / `threshold_g` + `feedback_ok_text`; kiosk lukee staten kautta |
| M-A7 | **S1: viestiprofiilit / ympäristösävyt** | Kiosk-plan S1 | Vain vapaat smile/frown -tekstit | Profiilit `koulu`\|`buffet`\|`hotelli` *tai* selkeät per-ympäristö -tekstit; admin valitsee (koulu-sävy oletuksena) |
| M-A8 | **Staff-toiminnot vain Adminissa** — **hyväksytty** | Kiosk M3 lukittu 2026-09-22 | Taara/Nollaa myös kioskissa | Siirrä: Taara, reset-day, baseline, esittelymock Admin-UI:hin; kiosk display-only |
| M-A9 | **Päivän pienin g** + footer-labelit | UI-lock 2026-09-22 | `day.max_g`; label “Keskiarvo g / ruokailija” | Storage/API: `min_g`; kiosk footer: `kpl` · `kg` · `keskimäärin g / palautus` · `Päivän pienin g` (ei “tänään”); tyhjä → `—` |
| M-A10 | **Vaakakokoonpanot A / A+B / A+C / A+B+C / C** — **hyväksytty** | Käyttäjä 2026-09-22 | **Toteutettu** | Config `scale_layout`; kiinteät nimet; hostit Administa; C = data only, tilastot erillään; kiosk full-width A / split A+B / ei kioskia jos vain C |
| M-A11 | **Kenttäkohtaiset (i)-ohjeet Adminissa** — **hyväksytty** | Käyttäjä 2026-09-22 | **Toteutettu** (hover) | (i) + **hover**-tooltip FI |
| M-A12 | **Päivittäinen virta-aikataulu + päivän vienti/nollaus** — **hyväksytty** | Käyttäjä 2026-09-22 | **Skriptit tehty** (`install-power-schedule.sh`); Admin-kellot UI optional | Edge RTC + sammutustimer; YKV+näyttö katkaisija; docs/power-schedule.md |

### Should

| # | Ominaisuus | Lähde | Nykytila | Agentti 2 -työ |
|---|------------|-------|----------|----------------|
| S-A1 | **Monipiste (site_id / scale_id)** | Kilpailija Should 6; Agent 3 | `site_id` string | Eventeihin `site_id`/`device_id`; admin suodatus; ei vielä ketju-UI |
| S-A2 | **Käyttäjät / roolit** (admin vs katselija) | Kilpailija Should 7; Agent 3 | Ei auth | Yksinkertainen PIN/salasana admin-kirjoitukseen (kiosk ei tarvitse tare/reset-PIN:iä) |
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

**Periaate:** Admin kirjoittaa configin, lukee raportteja ja ajaa staff-toiminnot. Kiosk on **display-only** (`GET /api/state`). Ei kilpailevia kirjoittajia samoihin kenttiin.

| Endpoint | Kuluttaja | Oikeudet | Huom |
|----------|-----------|----------|------|
| `GET /api/state` | **Kiosk** (pääasiallinen) | luku | Vain kun A tai A+B; A full-width / A\|B split; day-stats A+B `min_g`. **Ei kiosk-statea** jos vain C |
| `GET /api/config` | Admin (+ työkalut) | luku | Koko `AppConfig` |
| `POST /api/config` | **Vain admin** | kirjoitus | Validointi `config.py`; hot-reload; kiosk näkee seuraavassa state-pollissa |
| `GET /api/health` | Admin | luku | Device health; laajenna → per-scale A/B/C (mode/conn vain täällä) |
| `GET /api/events?...` | Admin | luku | Kiosk ei tarvitse (käyttää staten day-stats) |
| `GET /api/stats/daily?...` | Admin *(tulossa)* | luku | Aggregaatit |
| `GET /api/export/...` / `POST /api/export/day` | Admin | luku/vienti | Kiosk ei vie |
| `POST /api/tare`, `/api/reset-day`, `/api/set-baseline` | **Vain admin** | kirjoitus | Ei kiosk-UI:ta tuotannossa (UI-lock 2026-09-22) |
| `POST /api/demo/*` | **Admin esittelytila** | kirjoitus | Ei live-kioskissa; mock/esittely Administa |

**Konfliktien välttäminen**

- Kynnys-/viesti-/teema-arvot: **yksi lähde** `data/config.json` via `POST /api/config`. Kiosk ei tallenna näitä.
- Tapahtumat: vain tilakone → `storage.add_event`. Admin ei luo fake-eventejä (paitsi ehkä tulevissa testeissä).
- `reset-day` / tare / demo: **vain Admin** — ei kaksois-UI:ta kioskissa.
- Uudet S2-kentät (`threshold_ok_g`, `threshold_frown_g`, `feedback_ok_text`): admin kirjoittaa → sisällytetään `snapshot()["config"]` → kiosk/tilakone lukee.
- Day-stats: kiosk/footer = **vain A+B** (lautashävikki). **C aina erillään** Admin-raporteissa (päivän tuotantohävikki kg). C:llä ei feedback-kenttää eventeissä (tai `feedback=none`). `min_g` vain diner-statuksessa.

---

## 4. Ei tehdä

| Aihe | Syy |
|------|-----|
| **AI-kamera / Throw & Go -keittiöpino** | Eri use case (Winnow/Orbisk/KITRO); ei prioriteetti lautashävikkikioskille |
| **Avaimet käteen -asennuspalvelu** | Liiketoiminta / Serve-tyyppinen palvelu, ei admin-UI |
| **Väripickerit / monimutkainen teemoitus** | Käyttäjä: S4 dark/light riittää nyt |
| **Kioskin display-layout, offline-grace UI** | Agentti 3 — admin toimittaa configin + staff-toiminnot; ei PIN-kioskia (display-only) |

---

## 5. Seuraava sprintti

Konkreettiset tehtävät järjestyksessä (5–8 kpl). Pieniä API/config-laajennuksia ensin, sitten admin-UI.

1. **S2 config-malli** — Varmista `threshold_ok_g`, `threshold_g`, `feedback_ok_text` (`config.py` + validointi); altista `GET/POST /api/config` + `snapshot()["config"]`.
2. **Admin UI: kolmiportaiset kynnykset + ok-teksti** — Kahdella kynnyksellä + ok-viestillä; dokumentoi kioskille (Agentti 3 toteuttaa tilakoneen `ok`-feedbackin).
3. **M-A10 vaakamalli** — Config: layouts A \| A+B \| A+C \| A+B+C \| C; kiinteät nimet; hostit Admin UI; C data-only + erilliset päivätilastot; kiosk full-width / split / **ei kioskia** (vain C); event `scale_id` a\|b\|c. **Tehty.**
4. **M-A11 (i)-hover** — Jokaisen muokattavan Admin-kentän viereen (i) + FI hover-tooltip. **Tehty.**
5. **M-A8 staff Adminissa** — Taara / Nollaa / baseline / esittelymock Admin-UI:hin; poista tuotantokioskin action-rivi.
6. **M-A9 `min_g`** — Päivätilasto + admin-yhteenveto: päivän pienin g; tyhjä → `—`.
7. **Device health per-scale (M-A5)** — Health `scales[]` (a/b/c + nimi + käyttötarkoitus); admin-ruudukko; mode/conn vain Adminissa.
8. **S1 viestiprofiili** + **jaksoaggregaatit** + **CSV jaksolle** / CO₂ / locale (jos aikaa).

**Sprintin ulkopuolelle (seuraava jono):** **M-A12 virta-aikataulu** (RTC + sammutus + export/reset; YKV/näyttö katkaisija), auth/roolit, trendikaaviot, hälytykset, event `site_id`/`device_id` -skeema, PDF, kategoriat.

---

*Backlog only. Ei suuria feature-toteutuksia tässä dokumentissa.*
