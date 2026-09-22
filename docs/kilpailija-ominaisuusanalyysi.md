# Kilpailija-ominaisuusanalyysi — lautashävikki / plate-waste

**Kohde:** Agentti 2 (admin-dashboard) ja Agentti 3 (kiosk / kosketus-UI)  
**Oma tuote:** havikkivaaka — asiakkaan lautashävikki palautuspisteessä (KERN KFP + YKV-02 KCP)  
**Päivitetty:** 2026-09-10  
**Lähteet:** oma koodi (`app/`, `system_architecture.md`, README), julkiset tuotesivut (biovaaka.fi, hukka.ai, sensire.com, winnow/orbisk/kitro/leanpath/positive carbon), aiempi TCO-canvas (8.9.2026). Hinnat jätetty lyhyiksi tai pois.

**Käyttötapauksen erottelu**

| Tyyppi | Esimerkit | Sopivuus omaan hankkeeseen |
|--------|-----------|----------------------------|
| Asiakaspalautuspiste + palaute | Biovaaka Serve, oma DIY, Leanpath Spark (diner engagement) | Korkea |
| Manuaalinen / SaaS-kirjaus | Hukka AI, Sensire, Biovaaka Flow | Keski (raportointi, ei automaattista kioskia) |
| Keittiöastia + AI-kamera | Winnow, Orbisk, KITRO, Positive Carbon, Leanpath AI floor | Matala (eri piste; ominaisuuksia voi lainata adminiin) |

---

## 1. Oma järjestelmä — vahvuudet

Nykyinen lab/dealer-kiosk (`app/server.py`, `state_machine.py`, `static/index.html`, SQLite):

- **Automaattinen lautashävikkipunnitus** palautuspisteessä (KCP `SI`-poll, live tai mock)
- **Lisäyskohtainen palaute** (ei koko astian paino): hymy &lt; kynnys, suru ≥ kynnys (oletus 300 g)
- **Kumulatiiviset lisäykset** samaan astiaan: baseline nousee tapahtuman jälkeen → seuraava annos ilman tyhjennystä
- **Settle-ikkuna** ennen luokittelua (live ~10 s, mock-demo 2 s)
- **Automaattinen tyhjennys + taara:** netto ≈ 0 yli `empty_away_s` → vaihe `away`; astia takaisin → KCP-taara, päivän kg ei kasva
- **Manuaalinen Taara** (`POST /api/tare`) ja **Nollaa päivä** (`POST /api/reset-day`)
- **Päivätilastot kioskissa:** kpl, kg, keskiarvo g/ruokailija, max g; kalenteripäivän vaihtuessa automaattinen nollautuminen näkymässä
- **Tapahtumien tallennus** SQLite: `ts`, `grams`, `feedback`, `day`
- **Ystävälliset virheilmoitukset** suomeksi (ei raakoja socket-virheitä UI:ssa)
- **Boot-kiosk:** systemd + LightDM autologin + Chromium kiosk-tila
- **Mock-tila** demoon ilman YKV:tä (+150 / +400 / Tyhjennä)
- **Konfiguroitavat kynnykset** ympäristömuuttujilla: `HAVIKKI_THRESHOLD_G`, `HAVIKKI_SETTLE_S`, `HAVIKKI_EMPTY_G`, `HAVIKKI_EMPTY_AWAY_S`
- **Omistus / ei SaaS-riippuvuutta** lab-hostilla; data paikallisesti

Vertailussa Serveen: sama ydin (palautuspiste + palaute + punnitus). Vahvuutena kevyt, omistettava stack ja selkeä tilakone.

---

## 2. Oma järjestelmä — aukot

Puuttuu tai on vain lab-tasolla verrattuna kilpailijoihin:

| Aukko | Missä kilpailijoilla on |
|-------|-------------------------|
| Pilvi- / admin-dashboard, historiaraportit, trendit | Biovaaka Serve/Pro, Hukka, Sensire, kaikki AI-keittiöpalvelut |
| Monitoimipiste / ketjunäkymä | Hukka Premium, Sensire, Winnow, Orbisk, Leanpath |
| Käyttäjät, roolit, kirjautuminen | SaaS-tuotteet yleensä |
| Kynnysten muokkaus UI:sta (ei vain env) | Biovaaka Serve (keittiö/koulu määrittelee rajat) |
| CSV/PDF-vienti, ESG/CO₂ | Hukka, Sensire, Winnow, Orbisk, Positive Carbon, Leanpath |
| Ruokakategoriat / hävikkilajit (lautas vs linjasto vs keittiö) | Hukka, Biovaaka Pro/Flow, Sensire, AI-järjestelmät |
| Hälytykset / sähköposti-briefingit | Leanpath Daily Briefings, Sensire poikkeamat |
| Vieraskielinen kiosk / saavutettavuus | Leanpath Spark / kansainväliset tuotteet |
| Vaihtoehtoiset palauteviestit / animaatio / digitaalinen signage | Hukka metsäanimaatio, Biovaaka View, Leanpath Spark |
| Offline-jono + synkronointi | Odottava tuotantotarve; SaaS olettaa verkkoa |
| API autentikointi, monilaite | Tuotanto-SaaS |
| Ruokalista / hinta / menekkiarvio | Hukka, Leanpath menu-link |
| AI-ruokalajitunnistus | Winnow, Orbisk, KITRO, Positive Carbon AI, Leanpath AI — **ei prioriteetti** omalle lautashävikkikioskille |
| Asennuspalvelu + huolto avaimet käteen | Biovaaka Serve |

---

## 3. Kilpailijoiden ominaisuusmatriisi

Merkinnät: **K** = kyllä / vahva, **O** = osittain / eri muodossa, **—** = ei / ei oleellista, **?** = julkisesti epäselvä.

| Ominaisuus | Me | Serve | Hukka | Sensire | Winnow | Orbisk | KITRO | Pos.C | Leanpath |
|------------|----|-------|-------|---------|--------|--------|-------|-------|----------|
| Automaattinen lautashävikki palautuksessa | **K** | **K** | O¹ | — | O² | — | — | — | **K**³ |
| Välitön asiakaspalaute (hymy/väri/viesti) | **K** | **K** | O⁴ | — | — | — | — | — | O⁵ |
| Kumulatiiviset lisäykset + auto-taara | **K** | ? | — | — | — | — | — | — | ? |
| Päivätilastot paikallisessa UI:ssa | **K** | **K** | O | O | **K** | **K** | **K** | **K** | **K** |
| Historialliset raportit / trendit | — | **K** | **K** | **K** | **K** | **K** | **K** | **K** | **K** |
| Monitoimipiste / organisaatio | — | **K** | **K** | **K** | **K** | **K** | **K** | **K** | **K** |
| Admin-dashboard | — | **K** | **K** | **K** | **K** | **K** | **K** | **K** | **K** |
| Käyttäjät / roolit | — | ? | **K** | **K** | **K** | **K** | **K** | **K** | **K** |
| Kynnysten konfigurointi | O⁶ | **K** | O | O | O | O | O | O | O |
| Vienti CSV/PDF | — | **K** | **K** | **K** | **K** | **K** | **K** | **K** | **K** |
| CO₂ / ESG-raportointi | — | O | O | O | **K** | **K** | O | **K** | **K** |
| Hävikkikategoriat / syyt | — | O⁷ | **K** | **K** | **K** | **K** | **K** | **K** | **K** |
| Ruokalista / hinta / menekki | — | O | **K** | — | **K** | **K** | O | **K** | **K** |
| Hälytykset / briefing | — | ? | O | **K** | O | O | O | O | **K** |
| Digitaalinen signage / animaatio | — | O⁸ | **K** | O | — | — | — | — | **K**⁵ |
| AI-ruokalajitunnistus (keittiö) | — | — | — | — | **K** | **K** | **K** | **K** | **K** |
| Mock / demo ilman HW | **K** | — | **K**⁹ | **K**⁹ | — | — | — | — | — |
| Boot-kiosk omalla HW:lla | **K** | palvelu | — | — | laite | laite | laite | laite | laite |

¹ Hukka: vaakaintegraatio + manuaalinen kirjaus; ei Serve-tyyppinen automaattikiosk oletuksena.  
² Winnow: post-consumer mahdollista, fokus keittiö Throw & Go.  
³ Leanpath: plate waste tracking + CV/partnership; diner engagement erikseen.  
⁴ Hukka: metsäanimaatio / infotaulu lautashävikin perusteella, ei välttämättä per-lautanen hymy.  
⁵ Leanpath Spark: digitaalinen signage + CTA ruokailijoille.  
⁶ Me: vain env/CLI, ei admin-UI.  
⁷ Serve-paketti voi sisältää muiden hävikkilähteiden seurannan; Pro/Flow kategorisoivat keittiössä.  
⁸ Biovaaka View: hävikki näkyviin isommilla näytöillä.  
⁹ Softa toimii ilman omaa älyvaakaa (kirjaus päätelaitteella).

**Lyhyt positiointi**

- **Biovaaka Serve** = lähin kilpailija ominaisuuksiltaan (sama use case).
- **Hukka / Sensire** = admin-/raportointi-inspiraatio ilman automaattikioskia.
- **Winnow / Orbisk / KITRO / Positive Carbon / Leanpath AI** = keittiödata, CO₂, monisite — lainaa raportointiin, älä kopioi kamerapinoa kioskiin.

---

## 4. Suositukset Agentti 2 (admin) — priorisoitu backlog

### Must

1. **Päivä-/viikko-/kuukausinäkymä** (kg, kpl, avg, smile%, frown%) — *miksi:* Serve/Hukka/Sensire; ilman tätä data jää vain kioskin alariviin.  
2. **Tapahtumalista + suodatus päivällä** — *miksi:* auditointi, demo, virheiden selvitys.  
3. **CSV-vienti** (päivä / jakso) — *miksi:* Sensire PDF/CSV; koulut ja ketjut tarvitsevat Excelin.  
4. **Kynnysten ja settle/empty-parametrien UI** (kirjoitus → API/config) — *miksi:* Serve antaa rajojen määrittelyn keittiölle; env ei riitä tuotantoon.  
5. **Laite-/piste-status** (connected, last_event, mode live/mock, virhe) — *miksi:* huolto; Leanpath/Sensire “device health”.

### Should

6. **Monipiste (site_id / scale_id)** — *miksi:* Hukka Premium, Sensire, Leanpath enterprise.  
7. **Käyttäjät: admin vs katselija** (yksinkertainen auth) — *miksi:* SaaS-standardi; estää kioskin Nollaa-väärinkäytön etänä.  
8. **Trendikaaviot** (7/30 pv) + smile/frown-jakauma — *miksi:* Hukka visualisointi.  
9. **CO₂-ekvivalentti** (kg-hävikki × kerroin, konfiguroitava) — *miksi:* Winnow/Orbisk/Leanpath ESG; kevyt kerroin riittää aluksi.  
10. **Sähköposti-/webhook-hälytys** (vaaka offline &gt; N min; päivän kg &gt; tavoite) — *miksi:* Sensire poikkeamat, Leanpath briefings.

### Could

11. **Hävikkikategoria** (vain lautas vs myöhemmin linjasto) — *miksi:* Hukka/Sensire/Pro.  
12. **Vertailu toimipisteiden välillä** — *miksi:* Winnow/Orbisk benchmarking.  
13. **Ruokalistajakso / “mikä oli menussa” -tagi päivälle** — *miksi:* Hukka menu; auttaa tulkintaa ilman AI:ta.  
14. **PDF-raportti johdolle** — *miksi:* KITRO/Sensire.  
15. **API-avain ulkoiseen BI:hin** — *miksi:* Hukka “avoimet rajapinnat”, Positive Carbon API.

---

## 5. Suositukset Agentti 3 (kiosk / kosketus) — priorisoitu backlog

### Must

1. **Kosketukseen optimoitu layout** — suuret hit-targetit, ei pieniä demo-nappeja live-tilassa (demo vain mock).  
2. **Selkeä palautevaihe** — väri + iso symboli + lyhyt teksti (nykyinen hymy/suru pohjana; Serve/Uusiouutiset: vihreä/keltainen/punainen).  
3. **Henkilökuntatoiminnot erilleen** — Taara / Nollaa PIN:n tai pitkään painalluksen taakse — *miksi:* estää asiakkaan “Nollaa”-painallukset.  
4. **Yhteyskatkon UI** — iso “Odottaa vaakaa” + ei harhaanjohtavia tilastoja — *miksi:* jo aloitettu; vahvista kosketusnäytölle.  
5. **Yksi kieli kerrallaan, konfiguroitava** (fi oletus; en/sv myöhemmin) — *miksi:* koulut / kansainväliset vieraat (Leanpath/kansainväliset).

### Should

6. **Viestivariaatiot / sävy** (koulu vs buffet vs hotelli) — *miksi:* Serve monessa sektorissa; Hukka leikkisä animaatio vs asiallinen teksti.  
7. **Kolmiportainen palaute** (hyvä / ok / paljon) — *miksi:* Serve/Uusiouutiset keltainen väli; pehmeämpi kuin binääri.  
8. **Näytä vain live-lisäys + päivän kg**, piilota tekninen mode/conn normaalikäyttäjältä (debug-tila erikseen).  
9. **Saavutettavuus:** korkea kontrasti, ei pelkkä väri; fonttikoko; mahdollinen äänetön tila — *miksi:* julkiset ruokalat.  
10. **Privacy:** ei kameraa, ei henkilötunnistusta; ei tallenna kuvaa lautasta — *miksi:* erottaudu AI-keittiöistä; GDPR-helppo myynti.  
11. **Offline-grace:** UI toimii viimeisellä snapshotilla; tapahtumat jonoon jos admin-synk lisätään — *miksi:* lab-verkko epävakaa.

### Could

12. **Biovaaka View -tyylinen “seinänäyttö”-tila** (vain päivän kg + tavoite, ei hymyjä) — *miksi:* View / Hukka animaatio / Leanpath Spark.  
13. **Animaatio / progress** (esim. “päivän tavoite”) ilman pelillistettyä PII:tä — *miksi:* Hukka metsä; motivointi.  
14. **Monikieli toggle** kioskissa (lippu/kieli-nappi) — *miksi:* hotellit.  
15. **Kaksi vaakaa / kaksi astiaa samassa UI:ssa** (prod: Pi + 2× YKV) — *miksi:* architecture.md prod-visio; Serve usein yksi piste mutta ketju skaalaa.  
16. **Äänipalaute** (valinnainen, hiljainen) — *miksi:* saavutettavuus; pidä oletus pois.

---

## 6. Jaetut / data-mallin tarpeet (Agentti 2 + 3)

Molemmat agentit tarvitsevat saman tapahtuma-/tilamallin. Ehdotus laajennukseksi nykyiseen SQLiteen ja `/api/state`-snapshotiin.

### Nykyinen `events` (säilytä)

| Kenttä | Tyyppi | Huom |
|--------|--------|------|
| `id` | int | PK |
| `ts` | ISO UTC | |
| `grams` | real | lisäyksen koko |
| `feedback` | text | `smile` \| `frown` (myöhemmin `ok`) |
| `day` | `YYYY-MM-DD` | paikallinen kalenteripäivä |

### Must-laajennukset

| Kenttä / entiteetti | Käyttö |
|---------------------|--------|
| `site_id` | monipiste admin |
| `device_id` / `scale_id` | 1–2 vaakaa / piste |
| `threshold_g` (snapshot eventtiin) | historiallinen tulkinta kun kynnys muuttuu |
| `phase` / `event_type` | `waste_add` \| `tare` \| `auto_tare` \| `day_reset` \| `away` (audit) |
| Config-store | `threshold_g`, `settle_s`, `empty_g`, `empty_away_s`, `feedback_show_s`, `locale`, `message_profile` |

### Should-laajennukset

| Kenttä | Käyttö |
|--------|--------|
| `co2_g` tai laskenta raportissa | ESG admin |
| `category` | `plate` (default) |
| `menu_tag` / `service_period` | aamiainen/lounas |
| `guest_message_id` | A/B viestivariaatiot |

### Jaettu API-sopimus (suositus)

| Endpoint | Kuluttaja | Sisältö |
|----------|-----------|---------|
| `GET /api/state` | Kiosk | Nykyinen snapshot + `live_addition_g`, `day`, `feedback`, `connected`, `config` (read) |
| `GET /api/events?from&to&site=` | Admin | Sivutettu lista |
| `GET /api/stats/daily?from&to` | Admin | Aggregaatit |
| `GET /api/export.csv?...` | Admin | Vienti |
| `GET/PUT /api/config` | Admin (+ kiosk lukee) | Kynnykset, locale, viestiprofiili |
| `POST /api/tare`, `/api/reset-day` | Kiosk (suojattu) | Nykyiset |
| `GET /api/health` | Admin | connected, last_poll, mode |

**Event-esimerkki (JSON)**

```json
{
  "id": 42,
  "ts": "2026-09-10T11:22:33+00:00",
  "day": "2026-09-10",
  "site_id": "eira-1",
  "device_id": "ykv-a",
  "event_type": "waste_add",
  "grams": 280.5,
  "feedback": "smile",
  "threshold_g": 300,
  "category": "plate"
}
```

**Kiosk-state (laajennus)** — säilytä taaksepäin yhteensopivuus: `weight_g` = live-lisäys UI:lle; `bin_weight_g` raaka.

---

## Lähteet (valikoima)

- Oma: `README.md`, `system_architecture.md`, `app/state_machine.py`, `app/server.py`, `app/storage.py`, `app/static/index.html`
- Biovaaka Serve / Pro / Flow / View — biovaaka.fi  
- Hukka AI tuote & hinnoittelu — hukka.ai  
- Sensire hävikin hallinta & dashboard — sensire.com  
- Winnow VisionAI / Throw & Go — winnowsolutions.com  
- Orbisk How it works / vertailut — orbisk.com  
- KITRO TARE — kitro.ch  
- Positive Carbon Weight / AI — julkiset artikkelit + vendor  
- Leanpath Plate Waste + Spark — leanpath.com  
- Aiempi TCO-canvas: `havikkivaaka-kilpailija-analyysi` (8.9.2026)

---

*Tämä dokumentti keskittyy ominaisuuksiin. Make-or-buy / TCO: erillinen canvas-analyysi.*
