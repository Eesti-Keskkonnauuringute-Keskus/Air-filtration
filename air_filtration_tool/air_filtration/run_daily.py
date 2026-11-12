"""DAILY production pipeline - the method used for the 2024 report (EKUK, Oct 2026).

    deposition_cell = 3.1536e-3/365 * sum_d  Vd(LAI)_d * LAI_d * C_d      (t, guidance convention)
                    = 8.64e-6 * sum_d Vd_d [cm/s] * C_d [ug/m3]

Inputs (all on the 1 km L-EST97 grid):
  C_d       Airviro daily-mean PM2.5 (monitoring-corrected NetCDF)
  Vd(LAI)_d Table A1 applied to every HOUR of ERA5-Land 10 m wind, averaged per day
  LAI_d     'hybrid'  : Sentinel-3 2024 seasonal course x PROBA-V summer peak  (main)
            'satellite': Sentinel-3 2024 LAI as is                            (sensitivity)
            'phenology': PROBA-V peak x class phenology profile                (legacy check)
            satellite/hybrid include the evergreen winter correction.
Allocation: deposition of a cell is split over the Statistics Estonia level-2
ecosystem types by area share; level 1 = aggregation of level 2.

Each heavy input is cached in <cache_dir>/daily_<year>/ so re-runs are fast and an
interrupted run resumes.

Run:  python -m air_filtration daily --config config_daily_2024.yaml
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import warnings
# all-NaN cells (sea, outside Estonia) are expected; their numpy warnings are noise
warnings.filterwarnings("ignore", message="Mean of empty slice", category=RuntimeWarning)
warnings.filterwarnings("ignore", message="All-NaN slice encountered", category=RuntimeWarning)
import numpy as np
import pandas as pd

from .config import Config
from . import daily_inputs as di, io_raster, report
from .aggregate import mass_balance_check
from .constants import (STAT_L2_CLASSES, ECOSYSTEM_TYPES_L1, UNIT_FACTOR_PER_SECOND,
                        SECONDS_PER_DAY)

log = logging.getLogger(__name__)

LAI_LABEL = {
    "hybrid": "Main estimate (hybrid LAI: Sentinel-3 seasonal course x PROBA-V peak)",
    "satellite": "Sensitivity (Sentinel-3 LAI)",
    "phenology": "Check (PROBA-V peak x phenology profile)",
}


def _cached(path: Path, builder):
    if path.exists():
        log.info("cache hit: %s", path.name)
        return np.load(path)
    arr = builder()
    np.save(path, arr)
    return arr


def prepare_inputs(cfg: Config) -> dict:
    """Build (or load from cache) all daily input stacks."""
    grid = di.grid_from_config(cfg)
    cdir = Path(cfg.cache_dir) / f"daily_{cfg.reference_year}"; cdir.mkdir(parents=True, exist_ok=True)
    days = di.year_days(cfg.reference_year)
    C = _cached(cdir / "conc_daily.npy", lambda: di.airviro_daily(cfg.conc_daily_path, cfg.conc_daily_var, grid))
    if C.shape[0] != len(days):
        raise ValueError(f"concentration has {C.shape[0]} days, expected {len(days)}")
    if not (cdir / "vdlai_daily.npy").exists():
        vd, wd = di.daily_vdlai_era5(di.era5_hourly_files(cfg), grid)
        np.save(cdir / "vdlai_daily.npy", vd); np.save(cdir / "wind_daily.npy", wd)
    VD = np.load(cdir / "vdlai_daily.npy")
    area = _cached(cdir / "ecosystem_area_m2.npy", lambda: di.ecosystem_fractions(cfg.ecosystem_extent_path, grid))
    if not (cdir / "lai_satellite_daily.npy").exists() and not list(Path(cfg.lai_dir).glob("*.nc")):
        from .acquire_lai import download_lai_dekads      # Sentinel-3 LAI dekads from the CDS
        download_lai_dekads(cfg.reference_year, cfg.lai_dir, cds_rc_path=cfg.cds_rc_path,
                            area=[59.9, 21.4, 57.3, 28.3])
    LS = _cached(cdir / "lai_satellite_daily.npy", lambda: di.satellite_lai_daily(cfg.lai_dir, grid, cfg.reference_year))
    mask = io_raster.boundary_mask(cfg.boundary_path, grid)
    peak = io_raster.reproject_to_grid(cfg.lai_peak_path, grid, "bilinear") if cfg.lai_peak_path else None
    tot = area.sum(2)
    frac = np.where(tot[..., None] > 0, area / np.maximum(tot[..., None], 1), 0.0)
    return dict(grid=grid, days=days, C=C, VD=VD, area=area, frac=frac, LS=LS, mask=mask,
                peak=peak, cdir=cdir)


def lai_for_mode(inp: dict, mode: str, cfg: Config):
    LS = inp["LS"]
    if mode in ("satellite", "hybrid"):
        if cfg.evergreen_winter_correction:
            LS = di.evergreen_correction(LS, di.evergreen_share(inp["frac"]), inp["days"])
        if mode == "satellite":
            return LS
        if inp["peak"] is None:
            raise ValueError("lai_mode 'hybrid' needs lai_peak_path")
        return di.hybrid_lai(LS, inp["peak"])
    return None  # phenology handled class-wise


def deposition(inp: dict, cfg: Config, mode: str, C=None):
    """Returns (cell deposition [ny,nx] in guidance units, supply by L2 class [30] t/yr)."""
    C = inp["C"] if C is None else C
    f = UNIT_FACTOR_PER_SECOND[cfg.output_unit] * SECONDS_PER_DAY
    X = np.nan_to_num(inp["VD"] * C)                               # [T,ny,nx]
    frac, mask = inp["frac"], inp["mask"]
    if mode == "phenology":
        phen = di.class_phenology_daily(inp["days"])                 # [30,T]
        D = np.einsum("dhw,kd->hwk", X, phen) * np.nan_to_num(inp["peak"])[..., None] * f
        supply = (D * frac * mask[..., None]).sum((0, 1))
        dep = (D * frac).sum(2)
    else:
        LAI = lai_for_mode(inp, mode, cfg)
        dep = np.nansum(X * np.nan_to_num(LAI), 0) * f
        supply = (dep[..., None] * frac * mask[..., None]).sum((0, 1))
    return np.where(mask, dep, np.nan), supply


def _tables(inp, results: dict, main: str, cfg: Config):
    names = [c[1] for c in STAT_L2_CLASSES]; l1 = [ECOSYSTEM_TYPES_L1[c[2]] for c in STAT_L2_CLASSES]
    area_km2 = (inp["area"] * inp["mask"][..., None]).sum((0, 1)) / 1e6
    l2 = pd.DataFrame({"code": [c[0] for c in STAT_L2_CLASSES], "ecosystem_type_l2": names,
                       "ecosystem_type_l1": l1, "area_km2": area_km2})
    for m, (_, sup) in results.items():
        l2[f"t_per_yr_{m}"] = sup
    tot = l2[f"t_per_yr_{main}"].sum()
    l2["share_pct_" + main] = l2[f"t_per_yr_{main}"] / tot * 100
    cols = [c for c in l2.columns if c.startswith("t_per_yr_")]
    lvl1 = l2.groupby("ecosystem_type_l1", sort=False)[["area_km2"] + cols].sum()
    lvl1 = lvl1.reindex(ECOSYSTEM_TYPES_L1).fillna(0.0).reset_index()
    for m in results:
        if m != main:
            lvl1[f"diff_pct_{m}_vs_{main}"] = (lvl1[f"t_per_yr_{m}"] / lvl1[f"t_per_yr_{main}"].replace(0, np.nan) - 1) * 100
    return l2, lvl1


def _write_grid_shapefile(inp, results, Ca, path):
    """1 km cell polygons inside the accounting area with concentration, deposition
    (all runs) and the dominant level-2 ecosystem type."""
    import geopandas as gpd
    from shapely.geometry import box
    g = inp["grid"]; tr = g.transform; m = inp["mask"]
    jj, ii = np.nonzero(m)
    x0 = tr.c + ii * tr.a; y0 = tr.f + jj * tr.e
    geoms = [box(a, b + tr.e, a + tr.a, b) for a, b in zip(x0, y0)]
    data = {"cell_x": (x0).astype(int), "cell_y": (y0 + tr.e).astype(int),
            "conc_1km": Ca[jj, ii].round(4)}
    if "C10_annual" in inp:
        data["conc_10km"] = inp["C10_annual"][jj, ii].round(4)
    short = {"hybrid": "dep_hyb", "satellite": "dep_sat", "phenology": "dep_phen"}
    for k, (dep, _) in results.items():
        name = short.get(k, "dep_" + k.replace("hybrid", "hyb").replace("_", "")[:6])
        data[name[:10]] = dep[jj, ii].round(6)
    dom = inp["area"].argmax(2) + 1
    data["eco_l2_dom"] = dom[jj, ii]
    data["eco_l2_shr"] = (inp["frac"].max(2)[jj, ii]).round(3)
    gpd.GeoDataFrame(data, geometry=geoms, crs=g.crs).to_file(path)


def run_daily(config_path: str | Path | None = None, cfg: Config | None = None) -> dict:
    """Full daily run. Pass a YAML path or a ready Config (used by the workflow runner)."""
    cfg = cfg if cfg is not None else Config.from_yaml(config_path)
    logging.basicConfig(level=logging.INFO)
    out = Path(cfg.output_dir); out.mkdir(parents=True, exist_ok=True)
    inp = prepare_inputs(cfg)
    modes = [cfg.lai_mode] + [m for m in cfg.sensitivity_lai_modes if m != cfg.lai_mode]
    results = {m: deposition(inp, cfg, m) for m in modes}
    main = cfg.lai_mode
    # annual-mean concentration diagnostic (effect of daily vs annual C)
    Cann = np.repeat(np.nanmean(inp["C"], 0)[None], inp["C"].shape[0], 0)
    _, sup_ann = deposition(inp, cfg, main, C=Cann)

    # ---- task 1.1.2: 1 km vs 10 km concentration input (same Vd, LAI, ecosystems) ----
    cmp_rows = []
    if cfg.compare_10km:
        C10 = np.stack([io_raster.aggregate_1km_to_block(c, 10) for c in inp["C"]]).astype(np.float32)
        results[f"{main}_10km"] = deposition(inp, cfg, main, C=C10)
        Cann10 = np.repeat(io_raster.aggregate_1km_to_block(np.nanmean(inp["C"], 0), 10)[None], inp["C"].shape[0], 0)
        _, sup_ann10 = deposition(inp, cfg, main, C=Cann10)
        cmp_rows = [
            {"concentration_input": "daily C (main method)", "t_1km": float(results[main][1].sum()),
             "t_10km": float(results[f"{main}_10km"][1].sum())},
            {"concentration_input": "annual-mean C", "t_1km": float(sup_ann.sum()), "t_10km": float(sup_ann10.sum())},
        ]
        for r in cmp_rows:
            r["diff_t"] = r["t_10km"] - r["t_1km"]; r["diff_pct"] = r["diff_t"] / r["t_1km"] * 100
        LAI_LABEL[f"{main}_10km"] = LAI_LABEL[main] + ", 10 km concentration"
        inp["C10_annual"] = Cann10[0]

    l2, l1 = _tables(inp, results, main, cfg)
    totals = {m: float(s.sum()) for m, (_, s) in results.items()}
    mb = mass_balance_check(totals[main], cfg.national_total_emissions_t)
    yr = cfg.reference_year
    summary = pd.DataFrame([{"run": m, "description": LAI_LABEL[m], "total_t_per_yr": totals[m],
                             "pct_of_national_PM25_emissions": (totals[m] / cfg.national_total_emissions_t * 100)
                             if cfg.national_total_emissions_t else None} for m in results]
                           + [{"run": f"{main}_annual_C", "description": "Main estimate with annual-mean C (diagnostic)",
                               "total_t_per_yr": float(sup_ann.sum()), "pct_of_national_PM25_emissions": None}])
    meta = {"reference_year": yr, "size_fraction": cfg.pm_fraction,
            "vd_approach": "advanced: Vd = Vd(LAI)(hourly wind) x LAI, Table A1",
            "temporal_resolution": "daily", "wind": f"{cfg.era5_wind_dataset} hourly 10 m",
            "concentration": str(cfg.conc_daily_path), "ecosystem_extent": str(cfg.ecosystem_extent_path),
            "lai_main": LAI_LABEL[main], "evergreen_winter_correction": cfg.evergreen_winter_correction,
            "grid": f"{cfg.grid_size} x {cfg.analysis_resolution} m, origin {cfg.grid_origin}, {cfg.crs}",
            "output_unit": cfg.output_unit, "summation_convention": cfg.aggregation_convention,
            "accounting_area": "county boundaries (boundary_path)", "mass_balance": mb.get("status")}
    xlsx = out / f"air_filtration_daily_{yr}.xlsx"
    with pd.ExcelWriter(xlsx, engine="openpyxl") as xw:
        summary.to_excel(xw, sheet_name="summary", index=False)
        l2.to_excel(xw, sheet_name="supply_level2_STAT", index=False)
        l1.to_excel(xw, sheet_name="supply_level1_reporting", index=False)
        if cmp_rows:
            pd.DataFrame(cmp_rows).to_excel(xw, sheet_name="compare_1km_10km", index=False)
        pd.DataFrame(list(meta.items()), columns=["field", "value"]).to_excel(xw, sheet_name="metadata", index=False)
    l2.to_csv(out / f"supply_level2_{yr}.csv", index=False)
    l1.to_csv(out / f"supply_level1_{yr}.csv", index=False)
    for m, (dep, _) in results.items():
        report.write_geotiff(dep, inp["grid"], out / f"PM25_deposition_{yr}_{m}.tif",
                             f"PM2.5 dry deposition {yr} ({m} LAI), guidance units (t/km2/yr per cell)")
    Ca = np.where(inp["mask"], np.nanmean(inp["C"], 0), np.nan)
    report.write_geotiff(Ca, inp["grid"], out / f"PM25_concentration_{yr}_annual_1km.tif", f"PM2.5 annual mean {yr}, ug/m3, 1 km")
    if "C10_annual" in inp:
        report.write_geotiff(np.where(inp["mask"], inp["C10_annual"], np.nan), inp["grid"],
                             out / f"PM25_concentration_{yr}_annual_10km.tif", f"PM2.5 annual mean {yr}, ug/m3, 10 km blocks")
    if cfg.write_shapefile:
        _write_grid_shapefile(inp, results, Ca, out / f"air_filtration_{yr}_1km_grid.shp")
    report.write_metadata(cfg, {"mode": "daily", "totals_t_per_yr": totals, "compare_1km_10km": cmp_rows,
                                "annual_C_total_t_per_yr": float(sup_ann.sum()), "metadata": meta},
                          out / f"run_metadata_daily_{yr}.json")
    log.info("totals: %s", {k: round(v, 2) for k, v in totals.items()})
    if cfg.make_figures:
        from .figures import report_figures
        report_figures(cfg, inp, results[main][0], out / "figures")
    return {"totals_t_per_yr": totals, "output_dir": str(out)}
