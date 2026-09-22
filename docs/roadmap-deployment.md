# Roadmap: testikokoonpano → tuotantokloonaus

**Status:** vaihe 1 live YKV+SAD kiosk todennettu Lenovolla (2026-09-22). Seuraava: vaihe 3 UI (dual-scale, admin) + vaihe 2/4 monistus puhtaalle Ubuntulle.  
**Periaate:** Lenovo-lab on *testikokoonpano*. Repo + skill [`havikkivaaka-kiosk-deploy`](../.cursor/skills/havikkivaaka-kiosk-deploy/SKILL.md) on tapa monistaa sama kiosk mihin tahansa (X)Ubuntu-koneeseen.

---

## Vaiheet

| Vaihe | Mitä | Missä | Valmis kun |
|-------|------|--------|------------|
| **1 — Testikokoonpano (nyt)** | YKV-02 + SAD-paino, tilakone, kiosk/admin lab-UI, offline-LAN admin | Lenovo E31-80 + lab `192.168.50.0/24` | **Live OK (2026-09-22):** paino SAD-calilla, hymy/suru, boot-kiosk |
| **2 — Repo = toistettava asennus** | Kaikki labissa tehdyt asennus- ja verkkoaskeleet skripteinä + dokumentoituna | Tämä git-repo | Puhdas Ubuntu + repo → bootstrap → sama käyttäytyminen kuin labissa (ilman manuaalista “muistinvaraista” työtä) |
| **3 — Lopullinen kiosk + admin** | Vasta **YKV-toimintatestin jälkeen**: layouts A / A+B / A+C / A+B+C / C, A full-width, ei kioskia jos vain C, admin hostit + (i)-hover, raportit (C erillään), kynnykset, health, PIN/auth tms. backlog | Kehitys Lenovolla (tai kloonilla), muutokset repoon | Hyväksytty dealer/demo-UI + admin kytkimellä |
| **4 — Kloonaus tuotantokoneelle** | Valmis testikuva → toinen miniPC / Ubuntu-host | ISO / bootable USB / skriptiasennus (alla) | Uusi kone buuttaa kioskiin ja yhdistyy YKV:hen ilman uudelleenkehitystä |

---

## Vaihe 1 — Testikokoonpano (nykytila)

- **Ei tuotantoasennus.** Lenovo + USB-Ethernet / kytkin on YKV-integraation ja softan koekenttä.
- Mock-tila (`--mock`, `mock.conf`) on UI-/admin-työtä varten **ilman** vaakaa; live-tila on YKV-hyväksyntää varten.
- Hardware-sidonnaisuudet (esim. `enp1s0`, IP `.10` / `.11`) dokumentoidaan labissa; tuotantokloonissa ne parametrisoidaan (`HAVIKKI_*`).

Katso: [`system_architecture.md`](../system_architecture.md), [`dealer-day-checklist.md`](dealer-day-checklist.md).

---

## Vaihe 2 — Repon kyvykkyys: puhdas Ubuntu → sama toiminta

**Tavoite:** kun YKV-testi Lenovolla on OK, **uusi puhdas Ubuntu/Xubuntu** saadaan vastaavaan tilaan vain reposta + dokumentoiduista skripteistä.

### Jo repossa (labin peilaus)

| Kyky | Polku |
|------|--------|
| Paketit (ssh, python3, chromium, dnsmasq, …) | `scripts/bootstrap-xubuntu.sh` |
| YKV-linkki (EEE, DHCP `.11`) | `scripts/enable-ykv-link.sh`, `disable-ykv-link.sh`, `havikki-boot-ykv.sh` |
| Systemd + LightDM autologin + Chromium kiosk | `scripts/install-kiosk-autostart.sh` |
| Manuaalinen mock/live | `scripts/start-kiosk.sh` |
| Sovellus + admin/kiosk | `app/` |
| Arkkitehtuuri / checklist | `system_architecture.md`, `docs/dealer-*` |

### Asennuspuhdas Ubuntu (tavoiteprosessi)

```bash
# 1. Asenna Ubuntu/Xubuntu (LTS suositus tuotantoon; lab voi olla uudempi)
# 2. Kopioi/clone repo → ~/havikkivaaka
cd ~/havikkivaaka
sudo ./scripts/bootstrap-xubuntu.sh
# 3. Aseta tarvittaessa: HAVIKKI_IFACE, HAVIKKI_HOST, HAVIKKI_HTTP_HOST, käyttäjä
sudo ./scripts/install-kiosk-autostart.sh
# 4. YKV CAT6 + reboot → kiosk; admin: http://<edge-ip>:8080/admin
```

### Vielä vahvistettava ennen “valmis kloonattavaksi”

- [ ] `bootstrap` + `install-kiosk-autostart` toimivat **puhtaalla** koneella ilman lab-spesifejä manuaaleja
- [ ] Verkkoliitäntä ja IP:t envillä / configilla (ei vain Lenovon `enp1s0`)
- [ ] Live YKV end-to-end checklist vihreänä (`docs/dealer-day-checklist.md`)
- [ ] Mock ↔ live -vaihto dokumentoitu ja toistettava
- [ ] (Myöhemmin) yksi “golden” asennuspolku README:ssä: *Clean Ubuntu install*

Repo on **ensisijainen** tapa toistaa ohjelmisto; levykuva (vaihe 4) on pakkaus/nopea käyttöönotto päälle.

---

## Vaihe 3 — Lopulliset kiosk- ja admin-muutokset

**Ajoitus:** vasta kun **vaihe 1 YKV-toimintatesti** on hyväksytty (oikea vaaka, ei vain mock).

Silloin viimeistellään mm. (**UI-lock 2026-09-22**):

- **Dual-scale kiosk (peilattu A\|B):** kaksi vaakaa + kaksi YKV:tä; A vasen / B oikea; oma live-paino (*Ruokahävikkisi tänään*) + itsenäinen palaute per vaaka; ei vaakanimiä näytöllä; FullHD 27″ display-only (ei kosketusta)
- **Kolmiportainen palaute:** hyvä / ok / paljon (smile \| ok \| frown); kannustavat koulusävytteiset tekstit configista
- **Alalaidan laskenta:** **yhteistilastot** molemmilta (ei vaakakohtaista erittelyä); neljä hieman pienempää korttia, luku + label **peräkkäin** (fonttikoot ennallaan): `kpl` · `kg` · `keskimäärin g / palautus` · `Päivän pienin g` (korvaa max g; ei “tänään”-sanaa labeleissa); tyhjä päivä → `—`
- **Kiosk display-only:** ei Taara/Nollaa eikä tekniikkastatusta (MOCK/YKV/yhteys); mock-demonapit vain esittelytilassa
- **Admin-näkymä:** raportit, kynnykset (3-portaiset), health **per scale A/B**, Taara / päivän nollaus / esittelymock; käyttö kytkimen kautta

Backlogit: `docs/admin-backlog-agentti2.md`, `docs/kiosk-kilpailija-esitys.md`.  
Monistus ilman UI-muutoksia: [`.cursor/skills/havikkivaaka-kiosk-deploy`](../.cursor/skills/havikkivaaka-kiosk-deploy/SKILL.md).

Älä lukitse tuotanto-ISO:a ennen dual/admin-toteutuksen hyväksyntää — UI-koodi vielä lab-yksivaakaa.

---

## Vaihe 4 — Kloonaus: ISO ja bootattava USB?

Kun testikokoonpano + lopullinen UI ovat valmiita, järjestelmä pitää pystyä siirtämään toiselle koneelle. Kaksi pääpolkua:

### A) Skriptiasennus (aina ylläpidettävä)

- Puhdas Ubuntu → `bootstrap` + `install-kiosk-autostart` + repo.
- **Plussat:** eri rauta, eri levykoko, versionhallinta, helppo päivittää gitillä.
- **Miinukset:** asennus kestää pidempään; vaatii Ubuntu-median erikseen.

### B) Levykuva / bootattava media (nopea “applianssi”)

| Tapa | Mitä se tekee | Sopivuus |
|------|----------------|----------|
| **Clonezilla** (tai vastaava) | Kloonaa *asennehtun* golden-levyn → USB/external → restore uudelle koneelle | Paras **1:1-kloonaukseen** samaan/samanlaiseen rautaan; bootattava Clonezilla-USB + image |
| **Custom ISO** (Cubic / `live-build`) | Räätälöity Ubuntu-asennusmedia, jossa paketit + havikki valmiina | Hyvä **asennus-USB**:lle eri koneille; ei ole “bit-perfect” Lenovo-klooni |
| Pelkkä “ISO nykyisestä juuresta” | Harvoin suoraviivaista; Remastersys-tyyppiset työkalut vanhentuneet | **Ei suositella** ensisijaiseksi |

**Suositus suunnitelmaan:**

1. Pidä **repo + skriptit** aina ajantasalla (vaihe 2) — tämä on totuus.
2. Kun vaihe 3 on valmis Lenovolla (tai golden-labilla): ota **Clonezilla-image** golden-asennuksesta → tallenna USB:lle / arkistoon → palauta tuotanto-miniPC:lle (nopea kenttäasennus).
3. Jos tarvitaan usein *asennusmediaa* eri rautaan: rakenna myöhemmin **custom ISO** (Cubic tai scripted live-build), joka ajaa samat bootstrap-skriptit first-bootissa — ei korvaa Clonezillaa 1:1-varmuuskopiona.

**Bootattava USB:** kyllä — joko Clonezilla-live + image -tikku, tai custom Ubuntu ISO kirjoitettuna USB:lle (`dd` / Balena Etcher / Ventoy). Molemmat ovat toteutettavissa; valinta riippuu siitä, kloonataanko *yksi golden-levy* vai asennetaanko *puhdas Ubuntu + havikki*.

### Turvallisuus / offline

- Tuotanto-LAN ilman internetiä; admin LAN-IP:llä.
- Imageen **ei** sisällytetä salaisuuksia gitistä erillään (myöhempi admin-PIN generoidaan asennuksessa).
- Lab-käyttäjä `sami` / lab-IP:t korvataan tuotantoparametreilla ennen golden-imagea.

---

## Yhteenveto päätöksistä

| Kysymys | Vastaus |
|---------|---------|
| Onko Lenovo tuotanto? | **Ei** — YKV- ja softatestikokoonpano |
| Miten uusi Ubuntu-kone? | Repo + `bootstrap` + `install-kiosk-autostart` (pakollinen kyvykkyys) |
| Milloin lopullinen UI? | **YKV-toimintatestin jälkeen** |
| Voiko ISO/USB-kloonata? | **Kyllä:** Clonezilla 1:1; custom ISO asennusmediaksi; repo säilyy lähteenä |
