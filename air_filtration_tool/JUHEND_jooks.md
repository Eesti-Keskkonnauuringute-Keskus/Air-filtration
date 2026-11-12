# Juhend: õhufiltratsiooni (PM2.5) arvutuse jooksutamine

> **Töövoo skeem:** `docs/toovoog.png` (sammud 0–5 ja mis skript millal käivitada).

Conda keskkond: `air-filtration` · Seadistusfail: `config_daily_2024.yaml`
Kõik käsud käivita kaustas `air_filtration_tool`. Seadistusfailis on teed selle kausta suhtes, `~` tähendab kodukausta.

---

## Ettevalmistus (ühekordne)

1. **Paigalda [Anaconda](https://www.anaconda.com/download) või Miniconda** ja loo keskkond (Anaconda Promptis, kaustas `air_filtration_tool`):
   ```bat
   conda env create -f environment.yml
   ```
2. **CDS-i konto** (Copernicuse Climate Data Store; tuule ja LAI automaatseks allalaadimiseks):
   - registreeru aadressil <https://cds.climate.copernicus.eu/> ja kopeeri profiililehelt oma API võti;
   - loo fail `%USERPROFILE%\.cdsapirc` kahe reaga:
     ```
     url: https://cds.climate.copernicus.eu/api
     key: <sinu-võti>
     ```
   - aktsepteeri CDS-i veebilehel andmestike **ERA5-Land hourly data** ja **Leaf area index and fraction absorbed of photosynthetically active radiation 10-daily gridded data** litsentsid. Muidu allalaadimine keelatakse.
3. **Sisendfailid** kausta `inputs\` (neid gitis ei ole):
   - `netcdf_a1d_korr.nc` – Airviro ööpäevakeskmised PM2.5 kontsentratsioonid, seirega korrigeeritud (**annab EKUK igal aastal**);
   - `stat_EU_II.tif` – Statistikaameti ökosüsteemide kaart, II tase.

   Tipp-LAI ja maakonnapiirid on repos kaasas (kaust `data\`, vt `data\README.md`). Tuul ja Sentinel-3 LAI laaditakse alla automaatselt.

---

## Kõige lihtsam: kõik sammud ühe käsuga (`run_air_filtration.py`)

```bat
conda activate air-filtration
cd <SINU_KAUST>\air_filtration_tool
python run_air_filtration.py --config config_daily_2024.yaml
```

Skript läbib sammud 0–5 (vt `docs/toovoog.png`). Iga sammu juures näitab see olemasolevate failide seisu ja küsib, mida teha. **Enter** valib suure tähega vaikevaliku, **q** katkestab.

| Samm | Mida näitab | Valikud |
|---|---|---|
| 0 Seadistus | kas sisendfailid on olemas | testid jah/ei |
| 1 Tuul | mitu kuufaili 12-st on olemas | kasuta olemasolevaid / laadi puuduvad / laadi kõik uuesti |
| 2 LAI | mitu dekaadifaili on olemas (~36) | kasuta olemasolevaid / laadi uuesti |
| 3 Eeltöötlus | iga vahemälufaili seis: OK / puudub / sisend on uuem | arvuta vananenud / kõik uuesti / vali ise / jäta nii |
| 4 Arvutus | olemasolevad kogusummad | kirjuta üle / vanad arhiivi ja arvuta / jäta olemasolevad |
| 5 Kaardid | kas kaardid on olemas | joonista uuesti jah/ei |

- Esimesel korral laaditakse CDS-ist alla tuul (30–60 min) ja LAI (mõni minut). Järgmised jooksud võtavad umbes minuti.
- Vaikevalik on alati mõistlik: olemasolevat kasutatakse ja puuduv või vananenud arvutatakse.
- Kui laadid tuule või LAI uuesti, märgib skript sellest sõltuva vahemälu ja arvutuse automaatselt vananenuks.
- **Midagi ei kustutata.** Kui valid „uuesti“, tõstetakse vanad failid kausta `cache\_vana\<aeg>\`. Kui valid väljundite puhul „arhiivi“, lähevad need kausta `_arhiiv\outputs_daily_YYYY_<aeg>\`. Need võid hiljem ise kustutada.
- `--auto` töötab küsimusteta ja kasutab vaikevalikuid. `--alates 4` alustab otse arvutusest. Kui `--config` puudub, küsib skript seadistusfaili.
- Sama töövoo saab käivitada ka käsuga `python -m air_filtration workflow --config …`.

**Oodatav tulemus (2024):** põhihinnang `hybrid` **206,43 t**, tundlikkus `satellite` **109,84 t**, 10 km kontsentratsiooniga 206,41 t; 4,6 % riigi PM2.5 heitest.

Allpool on üksikkäsud juhuks, kui soovid samme eraldi käivitada.

---

## Kumba keskkonda kasutada?

| | Anaconda Prompt | VS Code |
|---|---|---|
| Millal | kiire kordusjooks, lisaseadistust pole vaja | kui samal ajal vaatad või muudad seadistust ja koodi |
| Ettevalmistus | pole vaja | ühekordne (vt allpool) |
| Käsud | samad | samad |

### VS Code ühekordne seadistus
1. Ava VS Code-is kaust **File → Open Folder… → `air_filtration_tool`**.
2. Vajuta `Ctrl+Shift+P` → **Python: Select Interpreter** → vali **`air-filtration` (conda)**.
3. Ava terminal: **Terminal → New Terminal**.
   - Kui rea alguses on `(air-filtration)`, oled valmis.
   - Kui ei ole, vali terminali paremal ülal oleva `+` kõrvalt **Command Prompt** ja kirjuta `conda activate air-filtration`.
   - PowerShelli terminalis töötab `conda activate` alles pärast ühekordset käsku `conda init powershell` Anaconda Promptis ja VS Code'i taaskäivitamist. Lihtsam on kasutada Command Prompti.

> Käivita Pythonit alati aktiveeritud `air-filtration` keskkonnas. Muidu ei leia rasterio/GDAL oma teeke ja programm võib ilma veateateta kokku joosta.

---

## A. Kordusjooks (sama aasta, 2024)

1. **Ava keskkond**
   ```bat
   conda activate air-filtration
   cd <SINU_KAUST>\air_filtration_tool
   ```
2. **(Soovi korral) testid:** `pytest -q` → peab tulema `18 passed`.
3. **Arvutus:**
   ```bat
   python -m air_filtration daily --config config_daily_2024.yaml
   ```
   Puuduvad tuule- ja LAI-failid laaditakse CDS-ist automaatselt alla. Lõpus peab olema kirjas `"hybrid": 206.43…` ja `"satellite": 109.84…`.
4. **(Soovi korral) tuule kontrolltabel** (tunnine vs päeva- vs kuukeskmine tuul): `python tuul_2024.py --config config_daily_2024.yaml`
5. **Ainult kaardid uuesti** (nt kui muutsid kaardi kujundust failis `air_filtration\figures.py`):
   ```bat
   python -m air_filtration figures --config config_daily_2024.yaml
   ```
6. **Tulemused** on kaustas `outputs_daily_2024\`:
   - `air_filtration_daily_2024.xlsx`, lehed: `summary`, `supply_level2_STAT`, `supply_level1_reporting`, `compare_1km_10km`, `metadata`
   - `PM25_deposition_2024_hybrid.tif` / `_satellite.tif` / `_hybrid_10km.tif`
   - `air_filtration_2024_1km_grid.shp` (kõik tulemused 1 km ruudu kaupa)
   - `figures\fig1…fig6` (aruande kaardid)

> **Kui muutsid sisendandmeid** (uus Airviro fail, uus ÖS kaart, uued LAI failid), kustuta kaust `cache\daily_2024` või kasuta `run_air_filtration.py`, mis tuvastab vananenud vahemälu ise. Kui muutsid ainult seadistust (nt `lai_mode`), ei ole kustutamine vajalik.

---

## B. Uue aasta arvutus (nt 2025)

1. **Kopeeri seadistusfail:** `copy config_daily_2024.yaml config_daily_2025.yaml` ja muuda uues failis:
   ```yaml
   reference_year: 2025
   conc_daily_path: "inputs/netcdf_a1d_korr_2025.nc"   # EKUK-i uus Airviro ööpäevakeskmiste fail
   national_total_emissions_t: …                       # 2025 riiklik PM2.5 koguheide (t), NFR
   lai_dir: "cache/lai_2025"                           # eraldi kaust uue aasta LAI jaoks
   output_dir: "outputs_daily_2025"
   ecosystem_extent_path: "inputs/…"                   # kui on uus ÖS kaart
   ```
   Airviro faili muutuja nimi peab olema `a1d`, muidu muuda `conc_daily_var`. Failis peab olema üks väärtus iga aasta päeva kohta: 365 või liigaastal 366.
2. **Kõige lihtsam:** `python run_air_filtration.py --config config_daily_2025.yaml` – laadib tuule ja LAI alla ning arvutab. Või sammhaaval:
3. **Tuul** (ERA5-Land, tunnine, umbes 30–60 min):
   ```bat
   python tuul_2024.py --config config_daily_2025.yaml
   ```
   Skript töötab iga `reference_year` puhul, nimest hoolimata. Kui allalaadimine katkeb, käivita sama käsk uuesti ja see jätkab puuduvatest kuudest.
4. **LAI** (Sentinel-3, 10 päeva kaupa):
   ```bat
   python -c "from air_filtration.acquire_lai import download_lai_dekads as d; d(2025, 'cache/lai_2025', area=[59.9, 21.4, 57.3, 28.3])"
   ```
   Kontrolli, et kaustas `cache\lai_2025` on umbes 36 `.nc` faili. (Kui CDS-i võti on muus failis kui `~/.cdsapirc`, lisa `cds_rc_path='~/.cdsapirc_cds'`.)
5. **Arvutus:** `python -m air_filtration daily --config config_daily_2025.yaml`
6. **Kontrolli tulemust:** lehel `summary` peab mass balance olema `plausible` ja koguheite osakaal mõne protsendi suurusjärgus; kaardid on kaustas `outputs_daily_2025\figures`.

PROBA-V suvine tipp-LAI (`data\LAI_peak_PROBAV_20190630.tif`) jääb samaks. Kuidas seda Copernicuse originaalfailist uuesti teha, vt `data\README.md`.

---

## Levinumad probleemid

| Sümptom | Lahendus |
|---|---|
| `'conda' is not recognized` | kasuta Anaconda Prompti või VS Code'is Command Prompt terminali |
| `No module named air_filtration` | sa ei ole tööriista juurkaustas (`cd …\air_filtration_tool`) |
| Programm lõpeb ilma veateateta / `Windows fatal exception` | Python ei ole käivitatud aktiveeritud `air-filtration` keskkonnas |
| `Puuduvad kohustuslikud sisendid` | pane `netcdf_a1d_korr.nc` ja `stat_EU_II.tif` kausta `inputs\` või paranda teed seadistusfailis |
| `concentration has N days, expected M` | Airviro failis on vale päevade arv või vale `reference_year` |
| CDS allalaadimise viga | kontrolli `.cdsapirc` võtit ja et CDS-i veebilehel on mõlema andmestiku litsents aktsepteeritud |
| Tulemus ei muutunud, kuigi vahetasid sisendfaili | kustuta `cache\daily_<aasta>` |

## Mida MITTE kasutada
- **CAMS-i kontsentratsiooni** – ülehindab Eesti taset umbes 2,7×.
- **ERA5 kuukeskmiste tuult** – alahindab tuulekiirust, sest u- ja v-komponendid keskmistatakse eraldi.
- **ERA5 0,25° tuult** – rannikuruudud sisaldavad merd. Kasuta ERA5-Landi.

Täpsem meetodi kirjeldus: `README.md`.
