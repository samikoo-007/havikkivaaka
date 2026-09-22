# Kokoonpano-suositus (hankinta + asennus)

Suositus tuotanto-/demoasennukseen. Softa ja verkko: [`system_architecture.md`](../system_architecture.md), asennus: [`.cursor/skills/havikkivaaka-kiosk-deploy`](../.cursor/skills/havikkivaaka-kiosk-deploy/SKILL.md), päivärytmi: [`power-schedule.md`](power-schedule.md).

## Ostopaikka — KERN-vaa’at ja lähettimet

| Mitä | Missä |
|------|--------|
| **KERN**-punnitusalustat / kennovaaka-alustat | **[Prodi Oy](https://prodi.fi/)** — [KERN-tuotemerkki](https://prodi.fi/tuotemerkki/kern/) |
| **KERN YKV-02** digitaalinen punnituslähetin (Ethernet + KCP) | Sama: kysy Prodilta YKV-02 + yhteensopiva alusta |

**Prodi Oy**  
Valakkatie 2, 00780 Helsinki  
Puh. [0207 439 439](tel:+358207439439) · [prodi@prodi.fi](mailto:prodi@prodi.fi) · [prodi.fi](https://prodi.fi/)

Tilatessa mainitse käyttötarkoitus (lautashävikki / keittiön tuotantohävikki) ja että tarvitaan **YKV-02 Ethernet** (ei pelkkä USB-malli YKV-01, jos edge yhdistetään LAN-kytkimellä). Varmista Prodilta ajantasaiset mallit, kaapelit ja kalibrointipainot.

> Hinnat ja varastosaldot ovat myyjän sivulla / tarjouksessa — tätä repossa ei ylläpidetä.

## Softan vaakakokoonpanot (Admin)

Admin → **Kokoonpano** (`scale_layout`). Sallitut:

| Layout | Käyttö | Kiosk | Mitä hankitaan (min.) |
|--------|--------|-------|------------------------|
| **A** | Yksi palautuslinja | A koko leveys | 1× alusta + 1× YKV-02 |
| **A+B** | Kaksi rinnakkaista palautuspistettä | Peilattu A\|B | 2× alusta + 2× YKV-02 |
| **A+C** | Lautas + keittiön tuotantohävikki | A koko leveys | 2× alusta + 2× YKV-02 |
| **A+B+C** | Kaksi lautasta + keittiö | A\|B split | 3× alusta + 3× YKV-02 |
| **C** | Vain keittiö (ei diner-näyttöä) | Ei kioskia | 1× alusta + 1× YKV-02 |

Kiinteät nimet Adminissa: **Vasen lohko** (A) · **Oikea lohko** (B) · **Keittiön hävikki** (C). C = mittaus ilman ruokailijapalautetta; tilastot erillään A/B:stä.

## Suositeltu laitteisto (tuotanto)

### Edge (yksi kone)

| Osa | Suositus | Huom |
|-----|----------|------|
| PC | **GMKtec G3S** (N95, 16 Gt, 512 Gt) → Xubuntu | BIOS: **S5 RTC Wake / Fixed Time** (testaa `rtcwake`); Win11 pyyhitään |
| Näyttö | **LG 27MS500-B** 27″ FHD IPS | Display-only; virta **katkaisijalla** YKV:n kanssa |
| Verkko | **TP-Link TL-SG105** (5× Gigabit) | Offline LAN; admin toiselta PC:ltä |
| Virta | Ajastettu / manuaalinen **katkaisija** YKV + näyttö | Edge herää RTC:llä; ei samalla releellä oletuksena |

### Hankintamatriisi — layout **A** (1 piste)

Hinnat / saatavuus tarkistettu **2026-09-22** (sis. ALV). Vahvista myyjän sivulla ennen tilausta.

#### Proshop.fi — edge PC

| # | Tuote | Linkki | Hinta (arvio) | Huom |
|---|--------|--------|---------------|------|
| 1 | GMKtec G3S · Intel N95 · 16 Gt · 512 Gt · Win11 Pro | [Proshop 3444065](https://www.proshop.fi/Poeytaetietokoneet-Mini-PC-Barebone/GMKtec-G3S-Intel-N95-16GB-512GB-Windows-11-Pro/3444065) | ~392,85 € | Mukana HDMI + VESA. **1× RJ45 Gigabit** (ei kahta LAN:ia — myyntiteksti harhaanjohtava). RTC Fixed Time + `rtcwake` testattava. |

#### Verkkokauppa.com — näyttö, verkko, kaapelit, huoltonäppis

| # | Tuote | Linkki | Hinta (arvio) | Huom |
|---|--------|--------|---------------|------|
| 1 | LG 27MS500-B 27″ Full HD IPS | [990091](https://www.verkkokauppa.com/fi/product/990091/LG-27MS500-B-27-Full-HD-naytto) | ~99 € (kampanja → 4.10.2026; norm. 129 €) | HDMI mukana paketissa |
| 1 | TP-Link TL-SG105 5-port Gigabit | [347651](https://www.verkkokauppa.com/fi/product/347651/TP-LINK-TL-SG105-5-porttinen-kytkin) | ~21,99 € | Hallitsematon; riittää |
| 1 | Logitech MK270 näppis + hiiri | [161770](https://www.verkkokauppa.com/fi/product/161770/Logitech-MK270-nappaimisto-ja-hiiri) | ~30,99 € | Vain asennus/admin (kiosk display-only) |
| 3 | Fuj:tech CAT6A U/UTP 10 m | [878002](https://www.verkkokauppa.com/fi/product/878002/Fuj-tech-CAT6A-U-UTP-verkkokaapeli-10-m-valkoinen) | ~3 × 13,99 € | Edge↔kytkin, YKV↔kytkin, varalla/admin |
| 0–1 | Fuj:tech HDMI 5 m (valinnainen) | [914479](https://www.verkkokauppa.com/fi/product/914479/Fuj-tech-HDMI-2-1-8K-Certified-Ultra-High-Speed-Cable-5-m-Wh) | ~29,99 € | Tarvitaan vain jos PC ei VESA-näytön takana (G3S/LG tuovat lyhyen HDMI:n) |

**VK-tilaus yht. (ilman erillistä HDMI):** ~99 + 22 + 31 + 42 ≈ **194 €**  
**Proshop + VK (ilman erillistä HDMI):** ≈ **587 €** (+ toimitukset)  
**+ 5 m HDMI:** ≈ **617 €**

#### Kaapelointi (layout A)

```text
[YKV-02] --CAT6--\
[G3S]    --CAT6--+-- [TL-SG105] --CAT6-- [admin-läppäri tarvittaessa]
[LG]     --HDMI-- [G3S]
```

**A+B / A+C / A+B+C:** lisää 1 CAT6 + 1 YKV(+alusta) per lisävaaka; kytkin 5 porttia riittää A+B+admin (+1 varalla). Kolme vaakaa + admin → harkitse 8-porttia (esim. TL-SG108).

#### Ostojärjestys

1. Verkkokauppa.com (näyttökampanja + kytkin + kaapelit + MK270).  
2. Proshop G3S.  
3. Koneelle: Xubuntu LTS → RTC-testi → [`havikkivaaka-kiosk-deploy`](../.cursor/skills/havikkivaaka-kiosk-deploy/SKILL.md).

### Punnitus (Prodi / KERN)

| Osa | Suositus | Määrä |
|-----|----------|-------|
| Punnitusalusta / kennovaaka | KERN-yhteensopiva alusta (Prodilta) | 1–3 layoutin mukaan |
| Lähetin | **KERN YKV-02** (Ethernet) | 1 per alusta |
| CAT6 | Edge/kytkin ↔ kukin YKV | 1 per lähetin |
| Kalibrointipaino | Referenssi SAD-caliin (esim. 20–50 kg, paikallisesti) | 1 |

Käyttöönotto / SAD: [`.cursor/skills/ykv-commissioning`](../.cursor/skills/ykv-commissioning/SKILL.md).

### Esimerkkikonfiguraatiot

**1) Koulu / buffet — yksi linja**  
Layout **A** · 1× YKV-02 + alusta · 1× näyttö · edge + kytkin · power-schedule 18:00/08:00.

**2) Ruuhkainen palautus**  
Layout **A+B** · 2× YKV-02 + alustat · peilattu kiosk.

**3) Lautas + keittiön tuotantohävikki**  
Layout **A+C** · 2× YKV-02 · kiosk vain A; C Admin-raporteissa.

**4) Vain keittiö**  
Layout **C** · ei diner-Chromiumia; mittaus + päivävienti Administa / timerillä.

## Ohjelmistoasennus (lyhyt)

```bash
cd ~/havikkivaaka
sudo ./scripts/bootstrap-xubuntu.sh
sudo ./scripts/install-kiosk-autostart.sh
# SAD-cal → data/ykv_sad_cal.json
sudo ./scripts/enable-ykv-link.sh
# Tuotannon päivärytmi (BIOS RTC wake ensin):
sudo ./scripts/install-power-schedule.sh
```

Admin LAN: `http://<edge-ip>:8080/admin` — otsikko, sijainti, layout, hostit, kynnykset.

## Liittyvät dokumentit

- [`system_architecture.md`](../system_architecture.md) — verkko, softa, virta
- [`power-schedule.md`](power-schedule.md) — RTC + sammutus + day-close
- [`roadmap-deployment.md`](roadmap-deployment.md) — lab → kloonaus
- [`dealer-day-checklist.md`](dealer-day-checklist.md) — demopäivä

> **Hankintamatriisi (Proshop + Verkkokauppa)** yllä § *Hankintamatriisi — layout A*. Hinnat vanhenevat; päivitä tarkistus päivämäärä tilauksen yhteydessä.
