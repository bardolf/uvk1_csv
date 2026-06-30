# Cheat sheet — UV-K1 / F4HWN na cesty (Slovinsko: hory + moře)

Stručná tahárna pro znalého uživatele. Pokrývá: upgrade firmware, co nastavit,
provoz na PMR pro rodinu a nouzové spojení na 2 m / 70 cm v horách.

> **Pravidlo č. 1 pro nouzi:** vždy nejdřív **telefon 112**. Funguje i bez SIM,
> bez kreditu a přihlásí se do jakékoli dostupné sítě. Horská služba ve Slovinsku
> (GRS) se aktivuje přes 112. Rádio je až **záloha**, když není signál.

---

## 1) Firmware: stojí 5.2.0 → 5.6.1 za upgrade?

**Krátce: ano, ale udělej to v klidu s rezervou před cestou, ne večer předtím.**

- 5.6.1 je tzv. **Fusion edition** — jediný build, který sloučil dřívější
  samostatné edice. Od 5.2.0 přibylo dost oprav (citlivost a chování scanu,
  demodulace FM/NFM, stabilita, screensaver/deep-sleep, detekce v K5Vieweru).
- **Riziko je nízké:** flash zapisuje jen do flash procesoru, **EEPROM
  (kanály + kalibrace) se nepřepisuje**. Kanály a `calibration.dat` tedy
  přežijí. Riziko vymazání hrozí jen při skoku z továrního / pre-5.x firmware
  (změna rozložení paměti) — to **není** tvůj případ.
- Podle release: pro stávající **5.x** uživatele stačí přeflashovat a (kdo
  používá CHIRP) aktualizovat přibalený CHIRP driver. **RESET ALL nedělej**,
  ledaže by se vysílačka po flashi chovala divně.

**Doporučení:**
- Máš-li do odjezdu víc než pár dní → upgraduj a otestuj.
- Odjezd za dveřmi a 5.2.0 funguje → **neflashuj pod tlakem**, 5.2.0 ti cestu
  zvládne.
- **Všechny 3 kusy nahraj na stejnou verzi**, ať se chovají identicky.

### Postup flashování (krok za krokem)

1. **Záloha (vždy):**
   ```bash
   ./uvk1_csv.py backup   -o backup_5.2.0.img        # raw image
   ./uvk1_csv.py download -o my_channels_backup.csv  # čitelná záloha kanálů
   ```
   `calibration.dat` už máš v repu — dobře.
2. Stáhni z [Releases](https://github.com/armel/uv-k1-k5v3-firmware-custom/releases/tag/v5.6.1)
   soubor firmware **.bin** (Fusion). (CHIRP driver jen pokud CHIRP používáš —
   pro tenhle projekt ho nepotřebuješ, programuješ přes CSV.)
3. **Vysílačku vypni.**
4. **Drž PTT a zapni** → rozsvítí se bílá LED (baterka) = **flash / DFU mód**.
5. Připoj USB-C k PC.
6. V **Chrome / Edge** otevři flasher: **https://armel.github.io/uvtools2/?mode=flash**
7. Vyber stažený **.bin**, zvol port (`/dev/ttyACM0`), **Connect → Flash**.
   Bílá LED během zápisu bliká. Nech doběhnout.
8. Vypni a zapni normálně.
9. **Ověř kanály vlastním nástrojem:**
   ```bash
   ./uvk1_csv.py download -o test_after.csv
   ```
   - Čte správně → hotovo.
   - Čte nesmysly → nová verze změnila rozložení EEPROM. Nevadí, zdroj pravdy
     je CSV: `./uvk1_csv.py upload -i my_channels.csv` a hotovo. (Pokud by ani
     to neselo, mapa paměti v `uvk1_csv.py` by chtěla aktualizovat — řekni.)

---

## 2) Co nastavit (menu tahárna)

Otevři menu, šipkami vyber položku, potvrď, EXIT zpět. Hodnoty jsou doporučení.

| Menu | Co to je | Hodnota pro tebe |
|------|----------|------------------|
| `STEP` | krok ladění | **12.5 kHz** (PMR i 2 m/70 cm) |
| `BANDW` (W/N) | šířka pásma | PMR = **N** (NFM); 2 m/70 cm FM = **W** |
| `TXP` | výkon (na F4HWN per kanál) | PMR = **LOW4 (500 mW)**; 2 m/70 cm = MID/HIGH |
| `R-CTCS` / `T-CTCS` | RX / TX CTCSS tón | dle kanálu (viz níže) |
| `R-DCS` / `T-DCS` | RX / TX DCS kód | dle kanálu |
| `SFT-D` | směr shiftu | převaděč: **–** ; simplex: OFF |
| `OFFSET` | velikost shiftu | 2 m = **0.600**, 70 cm = **7.600** |
| `SQL` | squelch | doma 3–5; v horách klidně **1–2** (slabé signály) |
| `TOT` | timeout vysílání | 60–120 s |
| `BCL` | busy lockout | OFF (na nouzi nechat OFF) |
| `MDF` | co displej ukazuje | NAME (jména kanálů) |
| `SAVE` | úspora baterie | ON (1:2 nebo 1:4) |
| `VOX` | hlasové vysílání | **OFF** (jinak vysílá samo) |
| `STE`/`RP-STE` | squelch tail | ON (čistší konec přenosu) |
| `MEM-CH` | uložit VFO → paměť | uložení naladěného kanálu |
| `CH-NAM` | pojmenovat kanál | |
| `DEL-CH` | smazat kanál | |
| `SC-ADD` | přidat do scan listu | užitečné pro PMR + 145.500 |
| `SetLck` (F4HWN) | zámek kláves | auto-lock dle chuti |

**Ruční naladění převaděče přímo ve vysílačce:** VFO → nalaď **výstupní** kmitočet
převaděče → nastav `STEP`, `BANDW=W`, `SFT-D=–`, `OFFSET` (0.600 / 7.600),
`T-CTCS` (tón, který převaděč vyžaduje) → `MEM-CH` ulož na číslo kanálu → `CH-NAM`
pojmenuj. **Tip:** programovat je pohodlnější přes CSV v tomhle projektu než
naťukáním v menu.

---

## 3) Provoz na PMR 446 (rodina) — legální, jednoduché

- 16 PMR kanálů, **NFM**, **500 mW (LOW4)**, krok 12.5 kHz. Bez licence.
- **Rodinný kanál se soukromím:** vyber jeden PMR kanál + **CTCSS tón** na RX i TX
  (v `slovenia.csv` je připravený kanál `FAM` = PMR 8 + 77.0 Hz). Tón = neslyšíš
  cizí provoz na stejném kanálu; **není to šifrování**, jen filtr.
- Domluvte si v rodině: **pracovní kanál** (FAM) + **náhradní** (např. PMR 6 bez
  tónu) pro případ, že by někdo „spadl" z tónu.
- **Dosah:** přímá viditelnost. Z hřebene do údolí klidně km až desítky km,
  v lese / zákrutech údolí klidně jen stovky metrů. Vyšší = lepší.

> ⚠️ Právní realita: UV-K1 **není** typově schválené PMR446 zařízení (odnímatelná
> anténa, vyšší výkon). Na PMR „jezdí", ale formálně to legální není. Pro běžné
> rodinné použití drž **LOW4 (500 mW)** a spíš **krátkou/stock anténu** — tím se
> držíš nejblíž limitu 0,5 W ERP a nerušíš.

---

## 4) Nouzové spojení v horách (záloha k 112)

**Pořadí kroků při nouzi:**

1. **Telefon 112.** Když nemáš signál, vystup na hřeben / vyvýšené místo a zkus
   znovu — často je to rychlejší než rádio. 112 bere i cizí síť bez SIM.
2. **Co nahlásit:** kde jsi (souřadnice z mapy v telefonu / název trasy /
   orientační bod + nadm. výška), co se stalo, kolik lidí, jaká zranění, číslo
   zpět na tebe.
3. **Rádio jako záloha (není-li signál):**
   - **2 m simplex volací: 145.500 MHz FM** — monitoruje ho hodně amatérů. Volej,
     poslouchej odpověď, požádej protistanici o **předání na 112 / GRS**.
   - **70 cm simplex volací: 433.500 MHz FM** — totéž pro 70 cm.
   - **Místní převaděč** (viz seznam níže / `slovenia.csv`) — má větší dosah, ale
     potřebuje správný **CTCSS tón** a často je v dosahu i tam, kde simplex není.
   - **PMR:** projeď scanem všech 16 kanálů a volej — můžeš chytit jiné turisty,
     ať zavolají 112.
4. **Maximalizuj dosah:** vystup výš (hřeben), anténa **svisle**, plný výkon
   (HIGH), nasaď **delší anténu (NA-771)**.
5. **Vizuální alpský nouzový signál** (když nic nefunguje): **6× signál za minutu**
   (píšťalka/světlo), minuta pauza, opakovat. Odpověď = 3× za minutu.

> ⚖️ Vysílat na amatérských pásmech **2 m / 70 cm legálně vyžaduje koncesi**
> (česká je ve Slovinsku platná jako host dle CEPT). **Příjem je vždy legální.**
> V **bezprostředním ohrožení života** ale platí mezinárodní výjimka — smíš použít
> jakýkoli prostředek a kmitočet k přivolání pomoci, bez ohledu na licenci.
> Mimo nouzi tedy na 2 m/70 cm vysílej jen s koncesí.

---

## 5) Antény

- Tvoje cca **40cm dvojpásmová** (nejspíš Nagoya NA-771 nebo klon) = lepší zisk na
  **2 m i 70 cm** než stock prcek. **446 MHz (PMR) je taky 70 cm**, takže funguje
  i na PMR.
- **Praktické dělení:**
  - PMR / běžné rodinné kecání → klidně **stock krátká** anténa (blíž limitu ERP,
    míň okatá).
  - Nouze / hledání dosahu na 2 m/70 cm → **NA-771**, vystup výš, anténa svisle.
- Nikdy nevysílej bez antény.

---

## 6) Převaděče pro oblast Kamnik (v `slovenia.csv`)

Základna **Kamnik** leží pod **Kamnicko-Savinjskými Alpami**. Triglav je v
**Julských Alpách** ~60–80 km na SZ — výletní vzdálenost, jiné kopce. Tomu
odpovídá výběr níže. Standardní shift v SI: **2 m = −0.6 MHz**, **70 cm = −7.6 MHz**.

| Kanál | Volačka | Výstup (RX) | Shift | CTCSS (TX) | Lokalita / pokrytí |
|-------|---------|-------------|-------|------------|--------------------|
| 20 | S55UKR | 438.675 | −7.6 | **123.0** ✓ | **Krvavec 1853 m** — přímo nad Kamnikem, hlavní lokál |
| 21 | S55VCE | 145.700 | −0.6 | **67.0** ✓ | Mrzlica 1122 m — široké pokrytí střední SI, EchoLink |
| 22 | S55VLJ | 145.775 | −0.6 | ? | Krim 1114 m — Ljubljanská kotlina |
| 23 | S55VTO | 145.7875 | −0.6 | ? | Kanin 2202 m — pro výlety k **Triglavu** / Julské Alpy |

✓ = ověřený tón. **?** = před použitím k vysílání ověř tón.

> ❗ Pro **příjem** tón nepotřebuješ (`R-CTCS` = OFF, uslyšíš vždy). Tón je nutný
> jen pro **vysílání** (`T-CTCS`), pokud ho převaděč vyžaduje. SI velmi často
> používá **123.0 Hz**. Aktuální údaje:
> - S51KQ: https://lea.hamradio.si/~s51kq/S5RPT.HTM
> - RepeaterBook (SI): https://www.repeaterbook.com/row_repeaters/index2.php?state_id=SI
>
> **Horská služba:** v Kamniku sídlí **GRS Kamnik**; aktivuje se přes **112**.
> Signál v údolích Kamnicko-Savinjských Alp je vesměs slušný, na hřebenech kolísá.

### Chorvatsko — Istrie (základna Vrsar / Koversada)

Vrsar je na západním pobřeží Istrie mezi Poreč (sever) a Rovinj (jih). HR shift je
stejný: **2 m = −0.6 MHz**. Tyhle tři jsou hlavně **na poslech** (RX tón OFF):

| Kanál | Volačka | Výstup (RX) | Shift | CTCSS (TX) | Lokalita / pokrytí |
|-------|---------|-------------|-------|------------|--------------------|
| 24 | 9A0VPO | 145.675 | −0.6 | ? | **Poreč** — nejblíž (~10 km sever) |
| 25 | 9A1AAM | 145.600 | −0.6 | ? | **Rovinj** — ~15 km jih |
| 26 | 9A0VRI | 145.700 | −0.6 | ? (~173.8) | **Učka 1396 m** — pokrývá celou Istrii |

> Kmitočty ověřené (RepeaterBook + 9A zdroje). **Tóny pro vysílání ověř** — v Istrii
> se objevuje **173.8 Hz**, ale ber to jako tip, ne jistotu. Na poslech tón netřeba.
> Aktuální HR seznamy: https://hrvhf.net/index.php/repetitori · http://www.radioz.org/repetitori/
> · [RepeaterBook HR](https://www.repeaterbook.com/row_repeaters/index2.php?state_id=HR)
>
> **Slovinské pobřeží** (kdybyste jeli přes Izolu/Koper): **S55VIZ Malija 145.7625,
> −0.6, CTCSS 77.0**.

> ℹ️ Soubor se jmenuje `slovenia.csv`, ale teď obsahuje i Istrii — je to prostě
> „CSV na celou cestu". Klidně ho přejmenuj, jen pak měň i příkaz při uploadu.

---

## 7) Odkazy

- Firmware (Releases): https://github.com/armel/uv-k1-k5v3-firmware-custom/releases
- Flasher (UVTools2): https://armel.github.io/uvtools2/?mode=flash
- Flashing wiki (egzumer, mateřský projekt): https://github.com/egzumer/uv-k5-firmware-custom/wiki/Flashing-the-firmware
- Programování kanálů: viz `README.md` v tomhle projektu (`./uvk1_csv.py upload -i slovenia.csv`)
