# Päivittäinen virta-aikataulu (tuotanto)

Lukittu malli: [`system_architecture.md`](../system_architecture.md) → *Daily power schedule*. Backlog **M-A12**.

## Mitä asennetaan

| Yksikkö | Rooli |
|---------|--------|
| `havikki-day-close.timer` | Illalla (oletus **18:00**): vienti + päivän nollaus → RTC-wake huomiseksi → `poweroff` |
| `havikki-day-boot-ensure.service` | Bootissa: jos eilinen jäi nollaamatta → vienti + nollaus; RTC uudelleen |
| `/etc/havikkivaaka/power-schedule.conf` | Kellonajat + API |

**Ei ohjaa** YKV-/näyttövirtaa — käytä **katkaisijaa** / ajastettua pistorasiaa.

## Asennus (edge Ubuntu)

```bash
cd ~/havikkivaaka
sudo ./scripts/install-power-schedule.sh
# kellot:
#   sudo HAVIKKI_POWER_OFF_TIME=18:00 HAVIKKI_POWER_ON_TIME=08:00 ./scripts/install-power-schedule.sh
```

Muokkaa myöhemmin `/etc/havikkivaaka/power-schedule.conf`, sitten päivitä timer:

```bash
sudo ./scripts/install-power-schedule.sh   # uudelleen (timer OnCalendar kirjoitetaan uudelleen)
```

## BIOS RTC wake

1. BIOS/UEFI: **Resume by RTC Alarm** / **Wake on Alarm** / **RTC Wake** = Enabled  
2. Varmista ettei ”Deep Sleep / G3 only” estä herätystä (konekohtainen).  
3. Testi:

```bash
sudo ./scripts/havikki-rtc-wake.sh status
# Armoi herätys ~3 min päähän (esim. jos kello 17:00 → 17:03):
sudo bash -c 'source /etc/havikkivaaka/power-schedule.conf; source ~/havikkivaaka/scripts/havikki-power-lib.sh; havikki_power_defaults; havikki_rtc_arm_next "$(date -d "+3 minutes" +%H:%M)"'
sudo ./scripts/havikki-day-close.sh --dry-run   # vienti+nollaus ilman poweroff
# Kun RTC-testi: sudo systemctl poweroff  — koneen pitäisi herätä asetetulla hetkellä
```

Tai: `sudo ./scripts/havikki-rtc-wake.sh arm 08:00` ja manuaalinen `poweroff`.

## Manuaaliset komennot

```bash
# Illan ajo ilman sammutusta (turvallinen testi)
sudo ~/havikkivaaka/scripts/havikki-day-close.sh --dry-run

# Boot-varmistus nyt
sudo systemctl start havikki-day-boot-ensure.service
sudo journalctl -u havikki-day-boot-ensure.service -n 40

# Timer-tila
systemctl list-timers 'havikki-day-close*'
tail -n 50 ~/havikkivaaka/logs/havikki-day-close.log
```

Stampit: `data/day-close-stamps/YYYY-MM-DD.ok` (estää tuplanollauksen).

## Illan / aamun järjestys

1. **18:00** softa: export + reset → RTC huomiseksi 08:00 → PC `poweroff`  
2. Henkilökunta / ajastin: **YKV + näyttö katkaisija OFF**  
3. **Aamu:** katkaisija ON → RTC herättää PC:n → kiosk-stack → (tarvittaessa boot-ensure)

## Poisto

```bash
sudo systemctl disable --now havikki-day-close.timer
sudo systemctl disable havikki-day-boot-ensure.service
sudo rm -f /etc/systemd/system/havikki-day-close.* /etc/systemd/system/havikki-day-boot-ensure.service
sudo systemctl daemon-reload
```
