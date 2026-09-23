# Jälleenmyyjätesti: Xubuntu ↔ YKV-02 Ethernet

## Lyhyt vastaus

**Kyllä, koneen voi valmistella etukäteen** niin että jälleenmyyjällä riittää CAT6 PC↔YKV + virta.  
Huomio: YKV-02 Ethernet on oletuksena **DHCP-asiakas** — pelkkä suora kaapeli ilman DHCP:tä **ei** anna YKV:lle IP:tä. Valmistele siksi yksi alla olevista tavoista.

**Yksi kaapeli kerrallaan:** Lenovon `enp1s0` on joko Mac-lab (`192.168.50.1`) **tai** YKV (`192.168.50.11`) — ei molempia samaan aikaan. Mac-varakuuntelu (alla) on kolmas topologia: Mac↔YKV, Lenovo irti.

**Eristetty verkko:** YKV-DHCP (`enable-ykv-link.sh`) on vain omalle kaapelille/kytkimelle. Skripti **kieltäytyy**, jos valitulla liitännällä on oletusreitti (talon LAN). Älä kytke YKV-NIC:iä koulun/toimiston pääkytkimeen.

---

## Ethernet-prep (Lenovo `enp1s0`)

| Asetus | Tavoite |
|--------|---------|
| Staattinen IP | `192.168.50.10/24` (NM manual, ei gatewayta) |
| **EEE pois** | NM `ethtool.eee-enabled=no` + boot-oneshot `ethtool --set-eee enp1s0 eee off` (`havikki-boot-ykv.sh`) |
| Reboot-tarkistus | Käynnistyksen jälkeen: `ethtool --show-eee enp1s0` → `EEE status: disabled`. Boot-asennus: `sudo ./scripts/install-kiosk-autostart.sh`. |

Lab-mock Macilta: `python3 tools/kcp_mock.py --port 2323` Macissa + Lenovolla `python3 -m app.server --host 192.168.50.1 --port 2323`. Oikea YKV: portti **23**, ei 2323.

---

## Xubuntu + vähän RAM:ia

| Suositus | Syy |
|----------|-----|
| **Xubuntu** OK | Kevyt, riittää PoC:lle |
| **Ei Dockeria** ensimmäiseen testiin | Säästää muistia |
| Python 3 + `nc` / `tools/kcp_client.py` | Riittää KCP-todistukseen |
| SSH valmiiksi | Voit auttaa Macilta |

Riittävä: ~2 Gt RAM + SSD/HDD. Älä asenna täyttä GNOME Ubuntu Desktopia.

---

## Kolme yhteystapaa (paras → varalla)

### A) Suora kaapeli + DHCP läppärillä (suositus “valmis laukkuun”)

PC tarjoaa DHCP:n; YKV saa IP:n automaattisesti.

| Laite | Asetus |
|-------|--------|
| PC `eth0` | staattinen `192.168.50.10/24` |
| dnsmasq | jakaa esim. `192.168.50.11` YKV:lle |
| YKV | oletus DHCP, CAT6 → PC |
| KCP | `192.168.50.11:23` |

Skripti: `scripts/enable-ykv-link.sh` (aja Xubuntussa rootina).

### B) Staattiset IP:t (jos YKV on jo konfiguroitu)

| Laite | IP |
|-------|-----|
| PC | `192.168.50.10/24` |
| YKV | `192.168.50.11` (JNEA/JNEK/JNEG tai web) |

Staattinen YKV vaatii yleensä ensin WiFi-AP:n (`192.168.4.1`) tai toimivan DHCP-linkin + KCP `JNEA`…

### C) USB (nopein pelastus jälleenmyyjällä)

YKV USB-B → PC, virta USB:sta. KCP sarjaportin kautta (laitetiedosto `/dev/ttyUSB*` / `/dev/ttyACM*`).  
Todistaa protokollan vaikka Ethernet-IP takkuaisi.

### D) Jälleenmyyjän kytkin + DHCP

Molemmat samaan verkkoon; selvitä YKV:n IP (reitittimen DHCP-lista / skannaus / Balance Connection). Portti **23**.

### E) Mac-varakuuntelu (diagnostiikka, ei live-pino)

Jos Ubuntu/Lenovo **ei** saa lähettimen dataa, kuuntele YKV:tä **Macilta** suoralla USB-Ethernet + CAT6 -kaapelilla (Lenovo irti). Mac `192.168.50.1/24` **ilman default-gatewayta** (Wi-Fi jää internetiin). DHCP vain lab-NIC:iin `.1:67` (ei `0.0.0.0`). Read-only KCP, ei taaraa/nollausta.

```bash
sudo ./scripts/enable-ykv-link-macos.sh
./scripts/listen-ykv.sh --mode auto --i1
sudo ./scripts/disable-ykv-link-macos.sh
```

Mac-kuuntelun onnistuminen **ei** tarkoita että Lenovon YKV-pino toimii. Ohje: [`docs/mac-ykv-listen.md`](mac-ykv-listen.md). Älä käynnistä ilman erillistä pyyntöä.

---

## Mitä pakata mukaan

- [ ] Xubuntu asennettuna, suomi-näppäimistö
- [ ] CAT6-kaapeli (auto-MDIX: normaali patch riittää)
- [ ] YKV:n USB-kaapeli + mahdollinen USB-virtalähde
- [ ] Repo / USB-tikku: `havikkivaaka` (`tools/`, `scripts/`)
- [ ] `python3`, `netcat-openbsd`, `dnsmasq` asennettuna
- [ ] Tämä ohje + `docs/kcp-protocol-model.md` + Mac-varalla `docs/mac-ykv-listen.md`

---

## Testisekvenssi paikan päällä (5 min)

1. YKV + alusta kytketty, virta OK.  
2. Ethernet PC↔YKV **tai** USB.  
3. Tapa A: aja `sudo ./scripts/enable-ykv-link.sh` → odota lease.  
4. `ping 192.168.50.11`  
5. `printf 'SI\r\n' | nc -v 192.168.50.11 23` → odota `S S` / `S D … g`  
6. `python3 tools/kcp_client.py --host 192.168.50.11 si`  
7. Paina alustaa / laita paino → arvon muutos.  
8. `… tare` / `… zero` savutesti.

Onnistuminen = ASCII-vastaus portista 23. UI/tilakone ei ole pakollinen tällä käynnillä.

---

## Mitä pyytää jälleenmyyjältä etukäteen

1. Onko demossa **YKV-02 + KFP** (tai vastaava alusta)?  
2. Saako käyttää **suoraa Ethernetiä** vai heidän kytkintään?  
3. Onko YKV:llä jo **staattinen IP**, vai tehdas-DHCP?  
4. USB-testi OK jos Ethernet ei nouse?
