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
| PC | miniPC / NUC / vastaava, **Ubuntu/Xubuntu Desktop** | BIOS: **RTC wake** (päiväsammutus) |
| Näyttö | Full HD ~27″ diner-seinä / teline | Display-only kiosk; virta **katkaisijalla** YKV:n kanssa |
| Verkko | Pieni **kytkin** (tai USB-Ethernet labissa) | Offline LAN; admin toiselta PC:ltä |
| Virta | Ajastettu / manuaalinen **katkaisija** YKV + näyttö | Edge herää RTC:llä; ei samalla releellä oletuksena |

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
