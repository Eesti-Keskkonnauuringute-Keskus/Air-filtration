# air_filtration — PM2.5 air-filtration ecosystem-service model

**Workflow diagram / töövoo skeem:** [`docs/toovoog.png`](docs/toovoog.png) (SVG: `docs/toovoog.svg`).
**Eestikeelne kasutusjuhend:** [`JUHEND_jooks.md`](JUHEND_jooks.md).

Calculates the **air filtration ecosystem service (PM2.5 dry deposition)** for Estonia
following the Eurostat ENV_EA guidance note, SEEA EA and Reg. (EU) 691/2011 (amended by
(EU) 2024/3024). Version **0.2.0** = the method of the report *Ökosüsteemi teenus:
õhu filtreerimine* (EKUK for Statistics Estonia, 2026, reference year 2024).

Expected result (2024): **main estimate 206.4 t PM2.5/yr** (hybrid LAI, 4.6 % of national
PM2.5 emissions), **sensitivity 109.8 t/yr** (Sentinel-3 LAI).

## Input data

| Input | Source | How to obtain |
|---|---|---|
| Daily PM2.5 concentration, 1 km, monitoring-corrected (`netcdf_a1d_korr.nc`, variable `a1d`) | Airviro model, **EKUK** | supplied by EKUK every year → put into `inputs/` |
| Ecosystem extent map, level 2 (`stat_EU_II.tif`, 10 m, 30 classes) | **Statistics Estonia** | your own data → put into `inputs/` |
| Hourly 10 m wind u/v (ERA5-Land, 0.1°) | Copernicus C3S, Climate Data Store | **downloaded automatically** (CDS account needed) |
| 10-daily LAI 2024 (Sentinel-3 OLCI/SLSTR V4.1, 300 m) | Copernicus C3S, Climate Data Store (`satellite-lai-fapar`) | **downloaded automatically** (CDS account needed) |
| Summer peak LAI (`data/LAI_peak_PROBAV_20190630.tif`) | Copernicus Land Monitoring Service, LAI 1 km V2 (PROBA-V) | **in this repository**; can be rebuilt, see [`data/README.md`](data/README.md) |
| County boundaries (`data/maakond_20230601.shp`) — accounting area | Maa- ja Ruumiamet | **in this repository** |
| National PM2.5 emissions (mass-balance check only) | NFR submission to CLRTAP | a number in the config (`national_total_emissions_t`) |

### CDS account (once)

1. Register at the [Climate Data Store](https://cds.climate.copernicus.eu/) and copy your
   API key from your profile page.
2. Create the file `~/.cdsapirc` (Windows: `%USERPROFILE%\.cdsapirc`) with two lines:
   ```
   url: https://cds.climate.copernicus.eu/api
   key: <your-personal-access-token>
   ```
3. Accept the licences on the download pages of **ERA5-Land hourly data**
   (`reanalysis-era5-land`) and **LAI and FAPAR 10-daily gridded data** (`satellite-lai-fapar`).
   Without this the download is refused.

If you keep the key in another file, set `cds_rc_path` in the config (e.g. `"~/.cdsapirc_cds"`).

## Quick start

```bat
conda env create -f environment.yml          :: once (or: conda env update -f environment.yml)
conda activate air-filtration
cd <folder>\air_filtration_tool              :: all commands are run from this folder

:: put inputs\netcdf_a1d_korr.nc and inputs\stat_EU_II.tif in place, then:
python run_air_filtration.py --config config_daily_2024.yaml
```

`run_air_filtration.py` goes through all steps (wind → LAI → pre-processing → calculation →
maps) and asks at every step whether to reuse existing files or recompute; `--auto` uses
the defaults without asking. The first run downloads ~0.6 GB from the CDS (wind 30–60 min,
LAI a few minutes); later runs take about a minute. Old files are never deleted, they are
moved to `cache/_vana/` or `_arhiiv/`.

Single steps:

```bat
python tuul_2024.py --config config_daily_2024.yaml              :: ERA5-Land hourly wind (+ Vd check table)
python -m air_filtration daily   --config config_daily_2024.yaml :: calculation + tables + rasters + maps
python -m air_filtration figures --config config_daily_2024.yaml :: maps only
pytest -q                                                       :: tests (18 passed)
```

Use the **Anaconda Prompt** (or a *Command Prompt* terminal in VS Code) on Windows. A Python
started outside the activated conda environment cannot load the GDAL libraries and may
crash silently.

## Method (daily, `run_daily.py`)

```
deposition_cell (t/km²/yr) = 8.64e-6 × Σ_d Vd_d (cm/s) × C_d (µg/m³)      8.64e-6 = 3.1536e-3/365
Vd_d = Vd(LAI)_d × LAI_d                                                  (guidance Eq. 2)
total (t/yr) = Σ cells                                                    (guidance convention)
```

| Input | Processing |
|---|---|
| C_d | Airviro daily means, area-average onto the 1 km grid |
| Vd(LAI)_d | Table A1 applied to **every hour** of ERA5-Land wind, averaged per day; each cell → nearest ERA5-Land land point |
| LAI_d (main, `hybrid`) | Sentinel-3 dekads → daily (linear); evergreen winter correction; seasonal course normalised to the cell's annual max × PROBA-V summer peak |
| LAI_d (sensitivity, `satellite`) | Sentinel-3 dekads → daily + evergreen winter correction |
| ecosystems | area of each level-2 class in every 1 km cell; cell deposition split by area share; level 1 = aggregation |
| accounting area | county polygons; open sea and the parts of Peipsi/Võrtsjärv outside the counties excluded |

Evergreen winter correction: evergreen share = coniferous + 0.5·mixed forest + 0.4·heathland;
for that share, LAI may not fall below the evergreen phenology profile × the cell's annual
max (Sentinel-3 gives LAI≈0 in winter for conifers because of snow/low sun).

Analysis grid: L-EST97 (EPSG:3301), 1000 m, upper-left (370000, 6620000), 380 × 250 cells.

### Lessons learned (do not repeat)

* **ERA5 `monthly_averaged_reanalysis` is unusable for wind speed** — it averages the u/v
  components, so √(ū²+v̄²) ≈ half of the real mean speed (2024: 2.1 vs 4.1 m/s) → Vd −66 %.
* Vd(LAI) is convex above ~7 m/s: monthly-mean wind −30 %, daily-mean wind −7 % vs hourly.
* ERA5 0.25° coastal cells contain sea → overestimated wind on the west coast/islands;
  use **ERA5-Land**. The CDS delivers ERA5-Land as a zip — `_open_uv` handles it.
* CAMS EAC4 (0.75°) is ~2.7× higher than Airviro over Estonia and has no urban structure;
  use the national Airviro concentrations.
* 1 km vs 10 km concentration input changes the national total by ~0.01 %.
* Sentinel-3 LAI peak values are ~half of PROBA-V/field LAI (conifer 1.7 vs 4.3) — this is the
  main uncertainty (hybrid vs satellite: −47 %).

## Outputs (`outputs_daily_2024/`)

| File | Content |
|---|---|
| `air_filtration_daily_2024.xlsx` | `summary`, `supply_level2_STAT`, `supply_level1_reporting` (Eurostat format), `compare_1km_10km`, `metadata` |
| `supply_level2_2024.csv`, `supply_level1_2024.csv` | same tables as CSV |
| `PM25_deposition_2024_{hybrid,satellite,hybrid_10km}.tif` | cell deposition (t/km²/yr, guidance convention) |
| `PM25_concentration_2024_annual_{1km,10km}.tif` | annual mean PM2.5 (µg/m³) |
| `air_filtration_2024_1km_grid.shp` | 1 km cells in the accounting area with all results and the dominant level-2 type |
| `figures/fig1…fig6` + `ratios.json` | report maps |
| `run_metadata_daily_2024.json` | full config + totals |

## Another year

Copy `config_daily_2024.yaml` to e.g. `config_daily_2025.yaml` and change `reference_year`,
`conc_daily_path` (new EKUK file), `national_total_emissions_t`, `lai_dir`
(e.g. `cache/lai_2025`), `output_dir` and, if there is a new map, `ecosystem_extent_path`.
Wind and LAI are downloaded for the new year automatically. See `JUHEND_jooks.md`, part B.

## Package layout

```
run_air_filtration.py  interactive step-by-step run (all steps)
tuul_2024.py           wind download + Vd averaging check (works for any reference_year)
config_daily_2024.yaml production configuration of the 2024 report
air_filtration/
  run_daily.py     daily pipeline (calculation, tables, rasters, shapefile)
  daily_inputs.py  daily C, hourly-wind Vd, Sentinel-3/hybrid LAI, ecosystem fractions
  workflow.py      interactive workflow behind run_air_filtration.py
  figures.py       report maps
  acquire_wind.py  ERA5-Land hourly download (CDS)
  acquire_lai.py   Sentinel-3 LAI download (CDS) + PROBA-V peak LAI builder
  constants.py     Table A1, unit factors, ecosystem types, STAT level-2 crosswalk, phenology
  config.py, vd.py, aggregate.py, io_raster.py, report.py, cli.py
data/              peak LAI + county boundaries (see data/README.md)
inputs/            EKUK concentration + STAT ecosystem map (not in git)
cache/             downloaded wind/LAI + pre-processed inputs (not in git)
tests/             pytest
```

## References

Eurostat ENV_EA TF guidance note on the air filtration ecosystem service; SEEA EA 2021;
Hirabayashi et al. (2012); Reg. (EU) 691/2011 & 2024/3024.
Data: Airviro (EKUK); ERA5-Land (Muñoz Sabater 2019, C3S CDS, doi:10.24381/cds.e2161bac);
C3S LAI and FAPAR 10-daily (doi:10.24381/cds.7e59b01a); CLMS LAI 1 km V2
(doi:10.2909/d5fdc595-2e03-4cbe-a39e-5f006f9cef07); Statistics Estonia ecosystem extent map
(2026); Maa- ja Ruumiamet county boundaries.

## License

Code: MIT, see [`LICENSE`](../LICENSE). Data in `data/` keep the licences of their providers
(see `data/README.md`).
