# Jälleenmyyjäpäivän checklist

> Tämä checklist koskee **testikokoonpanoa** (Lenovo + YKV). Tuotantokloonaus / ISO-USB: [`roadmap-deployment.md`](roadmap-deployment.md).

## Mukaan
- [ ] Lenovo + laturi
- [ ] CAT6 (suora PC ↔ YKV **tai** kytkin: edge + YKV + admin-PC)
- [ ] YKV USB-kaapeli + USB-virta varalle
- [ ] Repo ajantasalla (`~/havikkivaaka`)
- [ ] Tämä lista
- [ ] (Valinnainen) Admin-läppäri samassa LAN:ssa → `http://192.168.50.10:8080/admin`

## Paikalla (yksi vaaka + YKV-02, suora kaapeli)

**Boot-kiosk asennettuna** (`sudo ./scripts/install-kiosk-autostart.sh` kerran kotona):

1. [ ] Virta YKV + vaaka **ennen/kanssa** Lenovon käynnistyksen (DHCP lease bootissa)
2. [ ] CAT6 Xubuntu `enp1s0` ↔ YKV Ethernet (ei Mac-kaapelia)
3. [ ] Käynnistä Lenovo → auto-login → Chromium-kiosk (live KCP `.11:23`)
4. [ ] Tarkista tarvittaessa: `systemctl status havikki-ykv-link havikki-kiosk-app` · `ping -c 2 192.168.50.11`
5. [ ] Demo: lisäys &lt;300 g → hymy; ≥300 g → suru; tyhjennys; Taara

**Ilman boot-asennusta** (manuaalinen):

1. [ ] Virta YKV + vaaka; CAT6 `enp1s0` ↔ YKV
2. [ ] `cd ~/havikkivaaka && sudo ./scripts/enable-ykv-link.sh`
3. [ ] `ping -c 2 192.168.50.11` + KCP-smoke (`kcp_client.py --host 192.168.50.11 si`)
4. [ ] `./scripts/start-kiosk.sh --live`

## Failover
- Ethernet ei nouse → USB + ohje `docs/dealer-ethernet-prep.md`
- UI kaatuu → näytä CLI-painot (`kcp_client.py si`); backend: `sudo systemctl restart havikki-kiosk-app`
- Kiosk pois (SSH säilyy): `pkill -f 'user-data-dir=/tmp/havikki-chrome-profile'`; `sudo systemctl stop havikki-kiosk-app`

## Onnistumiskriteerit
- [ ] Vastaus TCP 23
- [ ] UI seuraa painoa
- [ ] Vähintään yksi hymy ja yksi suru
- [ ] Taara ≈ 0

## Lopuksi
```bash
# Boot-kiosk: riittää sammutus; tai palauta labiin Mac-kaapelille:
sudo systemctl stop havikki-kiosk-app
sudo ./scripts/disable-ykv-link.sh
# (halutessa) sudo systemctl start havikki-ykv-link   # DHCP taas YKV:lle
```

**Jäännösriski:** YKV kannattaa olla kaapelissa ja virrassa bootin aikana, jotta DHCP-lease tulee heti. Myöhäinen kytkentä toimii usein (dnsmasq jää päälle), mutta lease voi viivästyä.
