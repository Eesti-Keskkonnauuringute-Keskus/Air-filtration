"""2024. a tunnise tuule allalaadimine (ERA5-Land) ja Vd(LAI) kuuväärtuste kontroll.

Käivita (Windowsis, air-filtration conda keskkonnas, tööriista kaustas):
    python tuul_2024.py --config config_daily_2024.yaml

Teeb:
  1. laadib CDS-ist ERA5-Landi (era5_wind_dataset) tunnise 10 m tuule (u, v) 2024
     kohta, 12 kuufaili -> cache/era5land_hourly_wind_2024_MM.nc (CDS annab zip-i,
     mis pakitakse lugemisel lahti kausta *.unzipped; katkestuse korral jätkab)
  2. arvutab iga kuu Vd(LAI) üle TUNNISE tuule (tabel A1 rakendatakse igale tunnile)
  3. kirjutab <output_dir>/tuul_Vd_kontroll_2024.csv: tunnine vs päevakeskmine vs
     kuukeskmine tuul -> näitab keskmistamise viga
Mudeli jooks pärast seda (ööpäevane meetod, 2024. a aruanne):
    python -m air_filtration daily --config config_daily_2024.yaml
"""
import argparse, csv, logging
from pathlib import Path

from air_filtration.config import Config
from air_filtration.acquire_wind import download_era5_hourly_wind_year, monthly_vdlai_from_hourly

ap = argparse.ArgumentParser(); ap.add_argument("--config", default="config_daily_2024.yaml")
a = ap.parse_args()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
cfg = Config.from_yaml(a.config)
files = download_era5_hourly_wind_year(cfg)
_, _, _, rows = monthly_vdlai_from_hourly(files)
out = Path(cfg.output_dir); out.mkdir(parents=True, exist_ok=True)
fn = out / f"tuul_Vd_kontroll_{cfg.reference_year}.csv"
with open(fn, "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
h = sum(r["vdlai_hourly"] for r in rows); d = sum(r["vdlai_dailymean"] for r in rows)
mm = sum(r["vdlai_monthlymean"] for r in rows)
print(f"\nVd(LAI) aasta keskmine: tunnine {h/12:.4f} | päevakeskm. tuul {d/12:.4f} "
      f"({(d/h-1)*100:+.1f}%) | kuukeskm. tuul {mm/12:.4f} ({(mm/h-1)*100:+.1f}%) cm/s")
print(f"Kontrolltabel: {fn}")
