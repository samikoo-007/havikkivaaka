# Kiosk / kosketus-UI — kilpailijaominaisuusesitys

**Agentti 3** · ehdotus hyväksyttäväksi · **ei toteutusta tässä vaiheessa**  
**Peruste:** `docs/kilpailija-ominaisuusanalyysi.md` (Agentti 1) + nykyinen kiosk (`app/static/index.html`, `app/state_machine.py`)  
**Päivitetty:** 2026-09-10  
**Ajoitus:** lopullinen kiosk-toteutus **YKV-toimintatestin jälkeen** (Lenovo = testikokoonpano). Vaiheet: [`roadmap-deployment.md`](roadmap-deployment.md).

---

## 1. Mitä kioskissa on jo

Nykyinen asiakasnäkymä on toimiva lab-/dealer-kiosk palautuspisteeseen:

- Automaattinen lautashävikin punnitus (live YKV tai mock)
- Lisäyskohtainen palaute: hymy (&lt; kynnys) / suru (≥ kynnys), väri + symboli + suomenkielinen viesti
- Settle → palaute → hold; kumulatiiviset lisäykset samaan astiaan; auto-tyhjennys + taara
- Live-paino (“Ruokahävikkisi tänään”) + päivätilastot (kpl, kg, keskiarvo, max)
- Ystävälliset yhteysvirheet; Taara / Nollaa; mock-demopainikkeet
- Boot-kiosk (Chromium kiosk-tila)

**Aukko kilpailijoihin (Serve, Hukka-signage, Leanpath Spark):** kosketusoptimointi, henkilökuntatoimintojen suojaus, pehmeämpi palauteasteikko, digitaalinen signage / motivaatioanimaatio, monikieli ja selkeämpi “asiakas vs huolto” -erottelu.

---

## 2. Ylivertaiset kilpailijaominaisuudet kiosk / asiakasnäkymään

Prioriteetti: **Must** → **Should** → **Could**. Kukin kohta on ehdotus toteutettavaksi vasta hyväksynnän jälkeen.

### Must

#### M1 — Kosketukseen optimoitu layout
- **Kilpailijat:** Biovaaka Serve; Leanpath Spark (diner-näyttö)
- **Miksi:** Palautuspisteessä käyttäjä on seisten, käsissä tarjotin; pienet napit ja demokontrollit häiritsevät. Live-tilassa vain iso palaute + paino + päivän yhteenveto.
- **UX-luonnos:** Koko näyttö kaksi isoa aluetta (palaute | paino). Hit-targetit ≥ ~48–64 px. Mock-painikkeet (+150 / +400 / Tyhjennä) näkyvät vain `mode=mock`; live-tilassa ei demoriviä.

#### M2 — Selkeämpi palautevaihe (väri + iso symboli + lyhyt teksti)
- **Kilpailijat:** Biovaaka Serve / Uusiouutiset (vihreä–keltainen–punainen); nykyinen hymy/suru pohjana
- **Miksi:** Välitön, ymmärrettävä palaute on ainoa “tuotehetki” ruokailijalle — sen pitää olla luettavissa 2–3 metristä ilman ohjetta.
- **UX-luonnos:** Settling = keltainen “tasaantuu…”. Smile = vihreä + ☺ + 1 lyhyt lause. Frown = punainen + ☹ + 1 lyhyt lause. Teksti max ~2 riviä; ei teknisiä phase-koodeja asiakkaalle.

#### M3 — Henkilökuntatoiminnot erilleen (PIN / pitkä painallus)
- **Kilpailijat:** SaaS-kioskit erottavat staff-toiminnot; Serve-keittiö määrittelee rajat erikseen adminissa
- **Miksi:** Taara ja etenkin “Nollaa” (päivän nollaus) ovat vaarallisia asiakkaan sormille — yksi vahinko tyhjentää päivän tilastot.
- **UX-luonnos:** Normaalinäkymässä ei Taara/Nollaa. Huoltovalikko aukeaa esim. 3 s painalluksella nurkasta tai 4-numeroisella PIN:llä → sitten Taara / Nollaa / (debug). Sulkeutuu idle-timeoutilla.

#### M4 — Yhteyskatkon UI vahvistettuna
- **Kilpailijat:** Leanpath/Sensire “device health”; meillä jo ystävälliset virheet
- **Miksi:** Katkon aikana harhaanjohtava “0 g + vihreä hymy” tai vanhat tilastot ilman varoitusta heikentävät luottamusta.
- **UX-luonnos:** Iso keskeinen tila “Odottaa vaakaa” / “Ei yhteyttä”. Painoluku himmennetty tai “—”. Päivätilastot näkyvät harmaana tekstillä “viimeisin tila” tai piilotetaan kunnes connected.

#### M5 — Yksi kieli kerrallaan, konfiguroitava (fi oletus)
- **Kilpailijat:** Leanpath / kansainväliset diner-tuotteet; Serve monessa sektorissa
- **Miksi:** Kouluissa fi riittää; hotelli-/kampusympäristössä en/sv on myyntiargumentti ilman täyttä monikielitogglea heti.
- **UX-luonnos:** Locale configista (`fi` | `en` | `sv`). Kaikki UI-stringit yhdestä sanastosta; kielen vaihto ei asiakkaan arkirutiinia (ks. Could C3).

---

### Should

#### S1 — Viestivariaatiot / sävyprofiilit
- **Kilpailijat:** Hukka (leikkisä metsä/animaatio); Serve eri sektoreissa (koulu vs buffet)
- **Miksi:** Sama “Ota vähemmän”-viesti ei toimi alakoulussa ja hotellibuffetissa; sävy vaikuttaa siihen, otetaanko palaute vastaan vai ärsyynnytäänkö.
- **UX-luonnos:** Profiilit esim. `koulu` | `buffet` | `hotelli`. Smile/frown-tekstit vaihtuvat; värit/symbolit samat. Valinta admin/config — ei kioskin asiakasnappia.

#### S2 — Kolmiportainen palaute (hyvä / ok / paljon)
- **Kilpailijat:** Serve / Uusiouutiset (keltainen väli vihreän ja punaisen välissä)
- **Miksi:** Binääri hymy/suru tuntuu ankaralta ~280–320 g rajalla; “ok”-portaan pehmentää kokemusta ja ohjaa paremmin.
- **UX-luonnos:** Kaksi kynnystä (esim. hyvä &lt; 200 g, ok 200–300 g, paljon ≥ 300 g — arvot config). Keltainen kortti + neutraali symboli + lyhyt “ihan ok, voit vielä parantaa” -tyylinen viesti. Vaatii tilakoneen `feedback`-laajennuksen (`smile` | `ok` | `frown`).

#### S3 — Asiakkalle vain live-lisäys + päivän kg; tekniikka piiloon
- **Kilpailijat:** Serve/Spark näyttävät ruokailijalle tuloksen, ei “MOCK · kytketty”
- **Miksi:** Headerin mode/conn ja neljä pientä tilastokorttia kilpailevat huomion kanssa; asiakas tarvitsee “oma hävikki” + ehkä “yhteensä tänään”.
- **UX-luonnos:** Oletus: paino + palaute + yksi “Tänään: X kg / N ruokailijaa”. Mode, conn, max g, keskiarvo → debug/huoltovalikko (M3).

#### S4 — Saavutettavuus (kontrasti, ei pelkkä väri, fontti)
- **Kilpailijat:** Julkisten ruokailujen vaatimukset; Leanpath diner-näytöt
- **Miksi:** Väriblindit ja kirkas sali: pelkkä vihreä/punainen ei riitä; symboli + teksti pakollisia.
- **UX-luonnos:** Korkea kontrastiteema; symboli aina mukana; fonttikoko clamp jo nyt — varmista minimi. Valinnainen “äänetön” (ei ääntä; ks. C5).

#### S5 — Privacy-lupaus näkyväksi (ei kameraa, ei tunnistusta)
- **Kilpailijat:** Erottuminen Winnow/Orbisk/KITRO AI-kameroista; GDPR-myynti
- **Miksi:** Ruokailija näkee näytön ja saattaa epäillä kuvausta; lyhyt lupaus rakentaa luottamusta.
- **UX-luonnos:** Idle-tilassa pieni teksti: “Ei kameraa · ei henkilötietoja · vain paino.” Ei QR:ää, ei kirjautumista.

#### S6 — Offline-grace (viimeisin snapshot)
- **Kilpailijat:** Tuotanto-SaaS olettaa verkkoa; lab-verkko epävakaa
- **Miksi:** Hetkellinen API-katko ei saa tyhjentää näkymää nolliin kesken palautteen.
- **UX-luonnos:** Pidä viimeinen onnistunut `/api/state` ruudulla; näytä “yhteys heikko” -indikaattori; kun admin-synk tulee, tapahtumajono on Agentti 2 -asia.

---

### Could

#### C1 — “Seinänäyttö”-tila (Biovaaka View / Hukka / Spark)
- **Kilpailijat:** Biovaaka View; Hukka animaatio-infotaulu; Leanpath Spark
- **Miksi:** Ruokalan aulassa iso näyttö ilman hymyjä: vain päivän kg + tavoite motivoi ryhmää, ei yksilöä.
- **UX-luonnos:** Erillinen `display_mode=wall`: ei smile/frown, iso “Tänään X kg” + tavoitepalkki. Vaihto configilla / URL-parametrilla.

#### C2 — Keveä animaatio / päivän tavoiteprogress
- **Kilpailijat:** Hukka metsäanimaatio; Spark CTA
- **Miksi:** Motivaatio ilman pelillistettyä PII:tä (ei leaderboardeja nimillä).
- **UX-luonnos:** Idle: hidas progress kohti päivän tavoitetta (kg). Palautteen aikana animaatio pysähtyy; ei häiritse settleä.

#### C3 — Monikieli-toggle kioskissa
- **Kilpailijat:** Hotellit / kansainväliset kampukset
- **Miksi:** M5:n jälkeen nopea EN/SV-vaihto ruokailijalle ilman adminia.
- **UX-luonnos:** Pieni kielinappi nurkassa; vaihtaa sanaston heti; ei vaikuta dataan.

#### C4 — Kaksi vaakaa / kaksi astiaa samassa UI:ssa
- **Kilpailijat:** Serve skaalaa ketjulla; oma `system_architecture.md` prod-visio (Pi + 2× YKV)
- **Miksi:** Ruuhkainen palautuslinja — kaksi pistettä yhdellä näytöllä.
- **UX-luonnos:** Split-view A | B, kummallakin oma paino/palaute; tai automaattinen fokus aktiiviseen vaakaan.

#### C5 — Valinnainen hiljainen äänipalaute
- **Kilpailijat:** Saavutettavuus; harvinainen diner-kioskeissa
- **Miksi:** Näkörajoitteisille lyhyt beep/ääni; oletus OFF (meluisa ruokala).
- **UX-luonnos:** Config `sound=off|soft`; smile/frown eri lyhyt ääni; ei puhetta oletuksena.

---

## 3. Selvästi kioskin ulkopuolella (Agentti 2 / keittiö-AI)

Näitä **ei** ehdoteta kiosk-toteutukseen:

| Ominaisuus | Kuuluu |
|------------|--------|
| Historialliset raportit, trendit, CSV/PDF, CO₂/ESG | Admin (Agentti 2) |
| Monitoimipiste, käyttäjät/roolit, hälytykset/briefingit | Admin |
| Kynnysten muokkaus UI:sta, tapahtumalista, device health -dashboard | Admin (kiosk vain lukee configia) |
| Hävikkikategoriat, ruokalista/menekki, toimipistevertailu | Admin |
| AI-ruokalajitunnistus, kamera, Throw & Go -keittiöpino | Ei prioriteetti; eri use case (Winnow/Orbisk/KITRO) |
| Asennuspalvelu avaimet käteen | Liiketoiminta / Serve-tyyppinen palvelu, ei UI |

Kiosk kuluttaa `GET /api/state` (+ myöhemmin config-luku); kirjoitus vain suojattuihin tare/reset -toimintoihin.

---

## 4. Hyväksyntä

**Hyväksy ominaisuudet M1–M5** (kosketuslayout, palautevaihe, henkilökuntasuoja, yhteyskatko-UI, locale), niin ne toteutetaan ensimmäisenä kiosk-sprintissä.

Halutessasi mukaan heti: **S1–S3** (viestisävyt, kolmiportainen palaute, asiakasnäkymän siivous) — suositeltu “Should”-paketti samaan tai seuraavaan sprinttiin.

**Could (C1–C5)** jätetään odottamaan erillistä hyväksyntää seinänäyttö-/hotelli-/2-vaaka-tarpeen mukaan.

---

*Ehdotus vain. Ei muutoksia `index.html`-tiedostoon tai muuhun koodiin ennen erillistä toteutuspyyntöä.*
