---
name: havikkivaaka-logiikka
description: >-
  Hävikkivaaka v1 → v2.0 ydinlogiikka ilman sovelluskoodia: verkko/IP,
  ohjaus- ja tilakonelogiikka, salaisuudet, KERN KCP/SAD-säännöt, sekä
  mitkä ohjetiedostot siirretään uuteen koodikantaan. Käytä kun suunnittelet
  tai rakennat v2.0:aa hyläten vanhan repo-koodin.
---

# Hävikkivaaka — ydinlogiikka (v2.0-siirto)

Tämä dokumentti kuvaa **säännöt ja logiikan**, ei toteutusta.  
v2.0 saa hylätä kaiken nykyisen sovelluskoodin; alla oleva käyttäytyminen ja nimetty dokumentaatio ovat se, mitä pitää säilyttää tai tietoisesti muuttaa.

**Lähteet (v1):** `system_architecture.md`, `.cursor/skills/havikkivaaka-*`, `.cursor/skills/ykv-commissioning/`, `docs/kcp-protocol-model.md`, `docs/mac-ykv-listen.md`, `docs/power-schedule.md`.

---

## 0. Tuotteen ydin (yksi lause)

Asiakaspalauttaa lautasen bioastiaan → **KERN YKV-02** lukee kennon → edge-PC luokittelee **lisäyksen** (ei koko astian painoa) smile/ok/frown → päivän tilastot paikallisesti → henkilökunta hallitsee asetuksia erillisellä admin-selaimella **eristetyllä LAN:illa**.

Ei pilveä. Ei koulun/toimiston tuotanto-LAN:ia. Ei oletuksena internetiä.

---

## 1. Rajapinnat ja IP-osoitteet

### 1.1 Verkkomalli (kova sääntö)

```text
[YKV-02 …]──CAT6──┐
                  ├──[oma kytkin TAI suora kaapeli]──[Edge PC + kiosk-näyttö]
[Admin-laptop]────┘         vain 192.168.50.0/24 (lab/tuotanto-oletus)
```

| Sallittu | Kielletty |
|----------|-----------|
| Oma mini-kytkin tai suora CAT6 edge↔YKV | YKV-NIC rakennuksen pääkytkimeen |
| Admin samalla eristetyllä kytkimellä | `:8080` guest-Wi-Fiin / internettiin |
| DHCP **vain** YKV-suuntaisella NIC:llä | DHCP ifacellä jolla on default route |

Ilman kytkintä: **yksi kaapeli kerrallaan** — Mac↔edge **tai** edge↔YKV **tai** Mac↔YKV (diagnostiikka).

### 1.2 Oletusosoitteet (lab / tuotanto-skeleton)

| Rooli | Osoite | Portti / protokolla |
|-------|--------|---------------------|
| Edge (palvelin + kiosk) | `192.168.50.10/24` | HTTP **`0.0.0.0:8080`** |
| Mac / admin-dev | `192.168.50.1/24` | SSH edgeen; selain adminiin |
| YKV-02 (DHCP) | `192.168.50.11` | TCP **23**, KCP ASCII `\r\n` |
| Kiosk Chromium | `127.0.0.1:8080` | localhost edgellä |
| Admin selain (LAN) | `http://<edge-ip>:8080/admin` | PIN-header API:hin |

Monivaaka (max 3): jokaisella slotilla oma host:port (oletus A = `.11:23`; B/C tyhjä kunnes konfiguroitu). Sallitut layoutit: **`a` | `a_b` | `a_c` | `a_b_c` | `c`**.

### 1.3 HTTP-pinnat (käyttäytyminen, ei koodi)

| Polku | Kuka | PIN? | Tehtävä |
|-------|------|------|---------|
| `GET /` + staattiset | Kiosk | Ei | Diner-UI |
| `GET /api/state` | Kiosk | Ei | Live-tila (paino, feedback, päivästats) |
| `GET /api/health` | Molemmat | Ei | Terveys |
| `GET /api/auth` | Admin-shell | Ei | Kertoo tarvitaanko PIN |
| `GET/POST /api/config` | Admin | Kyllä | Asetukset (hot-reload) |
| `GET /api/events`, export CSV/JSON | Admin | Kyllä | Raportit |
| `POST /api/tare`, `/api/zero` | Kiosk/admin | Suojattu | Taara / nolla (ei jätetapahtuma) |
| `POST /api/reset-day` | Admin | Kyllä | Päivän nollaus (+ valinnainen export ennen) |
| `POST /api/set-baseline` | Admin | Kyllä | Esitäytetty astia ilman jätelaskua |
| `GET /admin` | Admin | Shell julkinen; API PIN | Hallinta |

**Säännöt:**

- Staattiset tiedostot vain oman `static/`-juuren alta (path traversal estetty).
- JSON POST -body max **64 KiB**.
- Admin-auth: header **`X-Havikki-Pin`** (ei cookie — CSRF-torjunta eristetyllä LAN:illa).
- PIN puuttuu = avoin admin vain labissa; asennus **aina** kirjoittaa PIN:in.

### 1.4 YKV-linkki (DHCP)

- Edge-NIC: staattinen `.10/24`, **ei** default gatewaya YKV-linkillä.
- DHCP tarjoaa YKV:lle **`.11`** (dnsmasq tai vastaava).
- EEE (Energy Efficient Ethernet) **pois** Realtek-NIC:llä (linkki lepattää muuten).
- Jos ifacellä on default route → DHCP **kielletty** (lab-override vain tietoisesti).

### 1.5 Mac-diagnostiikka (ei live-stack)

Vain kun käyttäjä erikseen pyytää kuuntelua. Mac USB-Ethernet = `.1/24` **ilman** default gw; DHCP bind **vain** `.1:67` (ei koskaan `0.0.0.0`). Read-only KCP. Onnistunut Mac-kuuntelu ≠ Ubuntu-stack OK.

### 1.6 USB-varatie (käyttöönotto)

| | |
|--|--|
| Laite | `/dev/cu.usbserial-*` (Mac FTDI) tai Linux-vastaava |
| Sarja | **9600 8N1** |
| Käyttö | SAD-kalibrointi / signaalitesti ennen Ethernet-liveä |

---

## 2. Ohjauslogiikka

### 2.1 Roolit (sama prosessi, eri pinnat)

| Pinta | Saa lukea | Saa kirjoittaa |
|-------|-----------|----------------|
| **Kiosk** (`/`) | `/api/state` | Vain suojattu tare/reset-tyyppinen |
| **Admin** (`/admin`) | config, events, health, export | config, reset-day, baseline, hostit |

Ei vaadi kahta HDMI:tä. Offline = paikallinen kytkin.

### 2.2 Vaakaslottit A / B / C

| Slot | Merkitys | UI |
|------|----------|-----|
| **A** | Vasen lohko (diner) | Kiosk: full-width jos A yksin / A+C; A+B → split |
| **B** | Oikea lohko (diner) | Vain layoutissa A+B / A+B+C |
| **C** | Keittiön hävikki | **Data only**: ei smile/ok/frown; tilastot erillään. Vain C → **ei diner-kioskia** |

Pollaus: lyhyt KCP-timeout (~**0.4 s**); kuollut slot ohitetaan ~**5 s** jotta yksi offline-vaaka ei jäädytä muita.

### 2.3 Painolähde (kriittinen laitesääntö)

| Prioriteetti | Lähde |
|--------------|--------|
| 1 | KCP **`SAD`** + kalibraatiotiedosto → grammaksi |
| 2 | Tehdas-KCP **`SI`** kg (usein väärä / `JAS E0012` tällä hardwarella) |

**SAD-kaava (logiikka):**

```text
kg = (sad − sad_empty) / (sad_at_ref − sad_empty) × ref_kg
g  = kg × 1000 − soft_tare_g
```

Kalibraatio per fyysinen YKV+alusta-pari:

- Kentät: `sad_empty`, `sad_at_ref`, `ref_kg` (tyypillisesti 50 kg = 10+20+20).
- Tiedostonimet: `ykv_sad_cal_{a|b|c}.json` tai jaettu `ykv_sad_cal.json`.
- **Älä** kopioi toisen yksikön cal-tiedostoa uudelle kennolle.
- Manuaalinen **Taara** SAD-polulla = **ohjelmallinen offset** (`soft_tare`); pelkkä KCP `T` ei muuta SAD-grammoja.

### 2.4 Jätetilakone (per slot)

Vaiheet: **`idle` → `settling` → `feedback` → `hold` → (`away` → auto-tare → `idle`)**.

```text
[IDLE]   baseline ≈ 0 / tyhjä
           paino nousee ≥ start_delta_g  →  [SETTLING]

[SETTLING]
           odota settle_s (live ~10 s; mock voi olla lyhyempi)
           lisäys = paino − baseline   (EI koko astian paino)
           luokittele → kirjaa tapahtuma → baseline = nykyinen paino
           → [FEEDBACK] (diner) tai suoraan [HOLD] (C / data_only)

[FEEDBACK]
           näytä smile|ok|frown ~ feedback_show_s
           → [HOLD]

[HOLD]
           uusi nousu ≥ start_delta_g  →  [SETTLING]  (astiaa ei tarvitse tyhjentää)
           net ≤ empty_g kestää empty_away_s  →  [AWAY]

[AWAY]   (tyhjennys; ei jätetapahtumaa)
           astia palaa (nousu away-lattiasta ≥ start_delta_g
             TAI paino ≈ empty_bin_g ± tolerance)
           → auto-tare → baseline 0 → [IDLE]
```

**Luokittelu (per lisäys):**

| Ehto | Feedback |
|------|----------|
| `addition < threshold_ok_g` | `smile` |
| `threshold_ok_g ≤ addition < threshold_g` | `ok` |
| `addition ≥ threshold_g` | `frown` |

Oletusarvot (admin-säädettävät):

| Parametri | Oletus | Merkitys |
|-----------|--------|----------|
| `threshold_ok_g` | 200 g | smile→ok raja |
| `threshold_g` | 300 g | ok→frown raja |
| `settle_s` | 10 s | vakiintumisaika ennen tapahtumaa |
| `start_delta_g` | 40 g | uusi tapahtuma / paluu AWAY:sta |
| `empty_g` | 20 g | “lähes tyhjä” |
| `empty_away_s` | 20 s | tyhjennysvaiheen kypsyminen |
| `feedback_show_s` | 3.2 s | UI-ikkuna |
| `quantize_g` | 2 g | SAD-kohinan deadband |
| `stable_hold_s` | 0.75 s | arvo pidettävä paikallaan ennen settle-valmista |
| `empty_bin_g` | 0 (off) | tunnettu tyhjän astian massa |
| `empty_bin_tolerance_g` | 50 g | empty_bin-osuma |

**UI-paino** = `live_addition_g` (delta baselinesta), ei `bin_weight_g`.  
Päivän kg = tallennetut tapahtumat (SQLite WAL, `synchronous=FULL`).

Manuaalinen **Nollaa päivä** ≠ taara. Kalenteripäivän vaihtuessa päivästats päivittyvät.  
Esitäyttö: `prefill_waste_g` / set-baseline — taara ei nollaa päivän kg:ta.

### 2.5 Mock vs live

| Tila | Merkitys |
|------|----------|
| **mock** | UI-kehitys ilman YKV; `connected=true` ei todista laitetta |
| **live** | KCP host:23; ilman kaapelia `connected=false` on OK |

Älä sekoita mock-onnistumista live-laitetestaukseen.

### 2.6 Päivittäinen virta (tuotantosääntö)

| Komponentti | Sääntö |
|-------------|--------|
| Edge PC | Illalla: export + reset-day → RTC wake huomiseksi → `poweroff`. Aamulla BIOS RTC herättää. |
| YKV + näytöt | **Erillinen katkaisija** / ajastettu pistorasia — ei samaa relettä edgen kanssa oletuksena |
| Boot-varmistus | Jos illan close jäi väliin → export+reset bootissa |
| Stampit | Estä tuplanollaus (`YYYY-MM-DD.ok`) |

Oletusajat (konfiguroitavat): power-off **18:00**, power-on **08:00**.

### 2.7 Boot-järjestys (live)

1. Verkko online → YKV-linkki (EEE off + DHCP `.11`)
2. Kiosk-app → HTTP `0.0.0.0:8080`, KCP enabled hosts
3. Day-boot-ensure (missed close)
4. Autologin → Chromium kiosk `127.0.0.1:8080`
5. Illalla: day-close timer

### 2.8 Turvallisuuslogiikka (eristetty appliance)

Threat model = joku **samalla eristetyllä kytkimellä**, ei internet. Silti:

1. `/static/` containment  
2. Admin PIN headerissä  
3. Body cap 64 KiB  
4. DHCP ei default-route -ifaceen  
5. SQLite WAL + FULL  
6. Poll ei jäädy yhteen kuolleeseen vaakaan  

TLS ei ole vaatimus ilman uplinkia. Älä “korjaa” `0.0.0.0`-bindiä `127.0.0.1`:ksi jos LAN-admin tarvitaan.

---

## 3. Avaimet, salasanat ja KERN KCP

### 3.1 Salaisuudet / tunnukset

| Nimi | Missä | Käyttö |
|------|-------|--------|
| **`HAVIKKI_ADMIN_PIN`** | `/etc/havikkivaaka/env` (chmod 600), **ei gitiin** | Admin API: header `X-Havikki-Pin` |
| SSH lab | host-kohtainen käyttäjä (lab: edge `192.168.50.10`) | Hallinta / rsync — ei osa tuotelogiikkaa |
| KCP | **Ei salasanaa** TCP 23:lla | Avoin ASCII KCP eristetyllä linkillä |
| YKV WiFi-AP (tehdas, harvoin) | Manuaali: AP `AI-Thinker_…`, UI `192.168.4.1` | Verkkoasetukset; ei kiosk-polku |

**Älä** committaa: `.env`, `/etc/havikkivaaka/env`, oikeita PIN-arvoja, KERN-vendor-PDF:ää, live `ykv_sad_cal*.json` (site-spesifi; example OK), tapahtumatietokantaa / PII:tä.

### 3.2 Ympäristömuuttujat (säännöt, ei arvoja)

| Muuttuja | Rooli |
|----------|--------|
| `HAVIKKI_IFACE` | YKV-Ethernet NIC |
| `HAVIKKI_HOST` / `_B` / `_C` | YKV IP:t |
| `HAVIKKI_HTTP_HOST` / `_PORT` | HTTP bind (oletus `0.0.0.0:8080`) |
| `HAVIKKI_USER` | Palvelu / autologin |
| `HAVIKKI_ADMIN_PIN` | Admin PIN |
| `HAVIKKI_MOCK` | Pakota mock |
| `HAVIKKI_SETTLE_S`, `HAVIKKI_THRESHOLD_G`, `HAVIKKI_EMPTY_*` | Boot-override tilakoneeseen |
| `HAVIKKI_ALLOW_DHCP_ON_DEFAULTED_IFACE` | Lab-escape DHCP-estoon |

Persistoidut asetukset: `data/config.json` (theme, tekstit, thresholdit, layout, hostit, `export_before_reset`, co2-factor, site_id, …).

### 3.3 KERN KCP — siirtoprotokolla

| Ominaisuus | Arvo |
|------------|------|
| Perhe | KERN Communications Protocol (KCP) ~1.1.2; manuaali 1.3.8 |
| Ethernet | TCP **23**, ASCII, komennot **UPPERCASE**, pääte **`\r\n`** |
| USB/RS-232 | 9600 8N1 |
| Luotettavuus | Odota vastausta ennen seuraavaa komentoa |
| Peruutus | `@` (ja `SIR` peruuntuu myös `S`/`SI`/`@`) |

**Vastauksen statuskirjaimet (yleiset):** `A` accept, `L` looginen virhe, `I` busy/ei nyt, `S` stable, `D` dynamic, `+`/`-` overload/underload, `ES` syntax.

**Painovastaus (`S`/`SI`/`SIR`):** 10 merkin oikealle tasattu lukukenttä, desimaali `.`, yksikkö perässä.

#### Komennot joita järjestelmä tarvitsee

| CMD | Käyttö | Huom |
|-----|--------|------|
| **`SAD`** | AD-lukema → grammaksi cal:lla | **Ensisijainen painolähde** |
| **`SI`** | Välitön paino / stabiilius | Fallback; usein epäluotettava kg tällä HW:llä |
| **`SIR`** | Jatkuva stream (~15 Hz) | Valinnainen; peruuta ennen T/Z |
| **`S`** | Odota stabiilia | |
| **`T` / `TI`** | Taara | SAD-polulla soft-tare + T |
| **`Z` / `ZI`** | Nolla | Diagnostiikka / päivän nolla |
| **`U` / `U g`** | Yksikkö | |
| **`I1` / `I2`** | Diagnostiikka / malli | |
| **`JNEA` / `JNEK` / `JNEG`** | Ethernet IP / mask / gw | Staattinen: järjestys JNEA→JNEK→JNEG; `JNEA 0.0.0.0` = DHCP |
| **`@`** | Peru stream / reset | |

**Ei MVP:lle:** peak (`SIM`), kappalelasku, `SMEM`, Level-2 adjustment pakollisena, digialusta `SJ`/`SJR`.

**Diagnostiikka read-only:** `SI` / `SIR` / `I1` — **ei** `T`/`Z` ellei erikseen pyydetä.

**Kalibrointi KCP:llä (`JAG*` / `JALL`):** usein `E0012` tällä hardwarella → **älä estä käyttöönottoa**; käytä SAD-cal. Älä teeskentele toista `JALL`-pistettä ilman painoa.

### 3.4 Kennokaapelointi (laitesääntö)

PCB vasemmalta oikealle: `E+  S+  OUT+  OUT−  S−  E−  Shield`.  
Labissa toimiva signaalipari: **`OUT+` / `OUT−`** laitteen oman ohjeen mukaan — älä “korjaa” toimivaa OUT± → S± vain PDF:n perusteella. Ensisijainen lähde: tarran / yksikön ohje + empirinen SAD-muutos kuormalla.

---

## 4. Mitä siirretään v2.0:aan (nimet, ei koodia)

v2.0-repoon **ei** tarvitse vanhaa `app/`-koodia. Siirrä (tai uudelleenkirjoita saman sisältöisinä) seuraavat **ohje- ja skeematiedostot**:

### 4.1 Pakollinen ydin (tämä + arkkitehtuuri)

| Tiedosto | Miksi |
|----------|--------|
| **`docs/skills/havikkivaaka_logiikka_SKILL.md`** | Tämä dokumentti — logiikan sopimus |
| **`system_architecture.md`** | Verkkomalli, boot, power, roolit (päivitä v2:lle) |
| **`docs/kcp-protocol-model.md`** | KCP-sovellusmalli (ei vendor-PDF) |
| **`data/ykv_sad_cal.example.json`** | SAD-cal skeema (tyhjät esimerkkiluvut) |
| **`data/README.md`** | Runtime-tiedostojen nimet ja säännöt |

### 4.2 Käyttöönotto ja laitteisto

| Tiedosto | Miksi |
|----------|--------|
| **`.cursor/skills/ykv-commissioning/SKILL.md`** | SAD-cal checklist, SI vs SAD |
| **`.cursor/skills/ykv-commissioning/wiring.md`** | Kennokaapelointi |
| **`docs/kokoonpano-suositus.md`** | Hankinta / BOM-suunta |
| **`docs/dealer-day-checklist.md`** | Jälleenmyyjäpäivän checklist |
| **`docs/dealer-ethernet-prep.md`** | Ethernet-valmistelu |

### 4.3 Deploy / lab / turvaportit (säännöt uudelleenkirjoitettaviksi skripteiksi)

| Tiedosto | Miksi |
|----------|--------|
| **`.cursor/skills/havikkivaaka-lab/SKILL.md`** | IP-taulu, mock/live, Mac-listen kielto |
| **`.cursor/skills/havikkivaaka-kiosk-deploy/SKILL.md`** | Clean Ubuntu -deploy checklist |
| **`.cursor/skills/havikkivaaka-production-gates/SKILL.md`** | Showstopper-portit ennen handoffia |
| **`docs/mac-ykv-listen.md`** | Mac↔YKV diagnostiikkasäännöt |
| **`docs/power-schedule.md`** | Illan/aamun virtalogiikka |
| **`docs/roadmap-deployment.md`** | Vaiheet test → clone/ISO |

### 4.4 Tuote-/UX-backlog (ei laitelogiikkaa, mutta v2-suunta)

| Tiedosto | Miksi |
|----------|--------|
| **`docs/admin-backlog-agentti2.md`** | Admin-vaatimukset |
| **`docs/kiosk-kilpailija-esitys.md`** | Kiosk-UX |
| **`docs/kilpailija-ominaisuusanalyysi.md`** | Kilpailijavertailu |

### 4.5 Älä siirrä v2:een “koodina”

- Koko `app/` (server, state_machine, kcp client, static HTML) — **uudelleenkirjoitus sallittu**, käyttäytyminen yllä.
- `scripts/*.sh`, `tools/*.py` — korvaa uusilla toteutuksilla; **säännöt** tulevat yllä olevista doceista.
- Live `data/config.json`, `events.sqlite3`, `exports/`, oikeat `ykv_sad_cal*.json`.
- `/etc/havikkivaaka/env` ja PIN-arvot.
- KERN-vendor-PDF (`KCP-ZB-e-v1.3.8.pdf`) — pidä paikallisena referenssinä, älä gittiin.

### 4.6 Runtime-skeemat jotka v2:n pitää toteuttaa uudelleen

| Artefakti | Minimisisältö |
|-----------|---------------|
| SAD cal JSON | `sad_empty`, `sad_at_ref`, `ref_kg` (+ valinnainen `note`) |
| Config | thresholdit, settle, layout, hostit, feedback-tekstit, export_before_reset |
| Events store | `ts`, `grams`, `feedback`, `day`, `scale_id` |
| Day export | CSV + JSON päivältä |
| Day-close stamp | `YYYY-MM-DD.ok` |
| Env | `HAVIKKI_ADMIN_PIN` + verkko-override |

---

## 5. v2.0 hyväksymiskriteerit (logiikka)

Uusi koodikanta on “yhteensopiva säännöillä” kun:

1. Eristetty `192.168.50.0/24` (tai dokumentoitu ekvivalentti); DHCP vain YKV-NIC:llä ilman default routea.  
2. YKV TCP 23, KCP `\r\n`; paino ensisijaisesti **SAD + cal**.  
3. Tilakone luokittelee **lisäyksen**, ei koko bin-painoa; AWAY + auto-tare ilman jätetapahtumaa.  
4. Layoutit A/B/C käyttäytyvät kuten §2.2.  
5. Admin PIN headerissä; kiosk `state`/`health` auki; static containment.  
6. Illan export+reset + boot-ensure + erillinen YKV/näyttö-katkaisija.  
7. Jokainen fyysinen vaaka-pari tarvitsee oman SAD-calin.

---

## 6. Agentille (v2-suunnittelu)

**Do:** toteuta uudelleen yllä olevat säännöt; pidä tämä tiedosto sopimuksena; päivitä `system_architecture.md` kun palvelut muuttuvat.  
**Don't:** kopioi v1-Python/HTML “koska se toimi”; sekoita Mac-listen / mock / live; luota `SI`-kiloihin ilman SAD-calia tällä hardwarella; altista DHCP tai HTTP tuotanto-LAN:iin.
