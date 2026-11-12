"""Fetch wind data from public APIs and reduce it to a per-cell wind time series.

Supported sources:
  * era5  : ERA5 hourly 10 m u/v components via the CDS (cdsapi). Preferred -
            hourly resolution captures the convex tail of Table A1.
  * eobs  : E-OBS daily mean wind speed 'fg' via the CDS. Acceptable lower bound.
  * cams  : CAMS wind via the Atmosphere Data Store (ads).

Credentials: CDS (ERA5/E-OBS) and ADS (CAMS) are SEPARATE data stores with
separate accounts/keys. If you keep separate rc files (e.g. ~/.cdsapirc_cds for
the Climate store and ~/.cdsapirc_ads for the Atmosphere store), point the config
at the right one via `cds_rc_path` / `ads_rc_path`; otherwise the default
~/.cdsapirc (or CDSAPI_URL / CDSAPI_KEY env vars) is used. VERIFY current dataset
identifiers/endpoints - Copernicus migrated to new CDS/ADS backends.
"""
from __future__ import annotations

from pathlib import Path
import logging
import tempfile
import zipfile

import numpy as np

log = logging.getLogger(__name__)


def _read_rc(rc_path: str | Path) -> dict:
    """Parse a .cdsapirc-style file into {'url':..., 'key':...}."""
    creds = {}
    with open(Path(rc_path).expanduser(), "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or ":" not in line:
                continue
            k, v = line.split(":", 1)     # split on FIRST colon (url contains '://')
            creds[k.strip()] = v.strip()
    if "url" in creds:
        creds["url"] = creds["url"].rstrip("/")   # avoid '/api//' double slash
    return creds


def cdsapi_client(rc_path: str | Path | None = None):
    """Build a cdsapi.Client, optionally from a specific rc file.

    Pass `rc_path` (e.g. ~/.cdsapirc_cds) to target one data store when you keep
    separate CDS and ADS credential files. If None, cdsapi's default resolution
    (~/.cdsapirc or CDSAPI_URL/CDSAPI_KEY env vars) is used.
    """
    import cdsapi
    if rc_path:
        creds = _read_rc(rc_path)
        if "url" not in creds or "key" not in creds:
            raise ValueError(f"{rc_path} must contain 'url:' and 'key:' lines")
        log.info("CDS client using rc file %s (url=%s)", rc_path, creds["url"])
        return cdsapi.Client(url=creds["url"], key=creds["key"])
    return cdsapi.Client()


def download_era5_wind(year: int, bbox_wgs84: list, out_nc: str | Path,
                       dataset: str = "reanalysis-era5-single-levels",
                       rc_path: str | Path | None = None) -> Path:
    """Download ERA5 hourly 10 m u/v for `year` over `bbox_wgs84` [N,W,S,E]."""
    out_nc = Path(out_nc)
    if out_nc.exists():
        log.info("ERA5 cache hit: %s", out_nc)
        return out_nc
    c = cdsapi_client(rc_path)
    c.retrieve(
        dataset,
        {
            "product_type": "reanalysis",
            "variable": ["10m_u_component_of_wind", "10m_v_component_of_wind"],
            "year": str(year),
            "month": [f"{m:02d}" for m in range(1, 13)],
            "day": [f"{d:02d}" for d in range(1, 32)],
            "time": [f"{h:02d}:00" for h in range(24)],
            "area": bbox_wgs84,           # [North, West, South, East]
            "format": "netcdf",
        },
        str(out_nc),
    )
    return out_nc


def download_era5_monthly_wind(cfg) -> Path:
    """Download ERA5 monthly-mean 10 m u/v for the reference year (CDS).

    Uses `reanalysis-era5-single-levels-monthly-means` (0.25 deg). For a finer
    land field switch the dataset to `reanalysis-era5-land-monthly-means` (0.1 deg).
    """
    from pathlib import Path as _P
    cache = _P(cfg.cache_dir); cache.mkdir(parents=True, exist_ok=True)
    out_nc = cache / f"era5_monthly_wind_{cfg.reference_year}.nc"
    if out_nc.exists():
        return out_nc
    bbox = getattr(cfg, "bbox_wgs84", [59.9, 21.5, 57.3, 28.3])
    c = cdsapi_client(cfg.cds_rc_path)
    c.retrieve(
        "reanalysis-era5-single-levels-monthly-means",
        {
            "product_type": "monthly_averaged_reanalysis",
            "variable": ["10m_u_component_of_wind", "10m_v_component_of_wind"],
            "year": str(cfg.reference_year),
            "month": [f"{m:02d}" for m in range(1, 13)],
            "time": "00:00",
            "area": bbox,                    # [N, W, S, E]
            "format": "netcdf",
        },
        str(out_nc),
    )
    return out_nc


def download_eobs_wind(year: int, out_nc: str | Path,
                       dataset: str = "insitu-gridded-observations-europe",
                       rc_path: str | Path | None = None) -> Path:
    """Download E-OBS daily mean wind speed 'fg'. (Whole-Europe file; subset later.)"""
    out_nc = Path(out_nc)
    if out_nc.exists():
        return out_nc
    c = cdsapi_client(rc_path)
    c.retrieve(
        dataset,
        {
            "product_type": "ensemble_mean",
            "variable": "wind_speed",
            "grid_resolution": "0.1deg",
            "period": f"{year}",
            "version": "27.0e",
            "format": "zip",
        },
        str(out_nc),
    )
    return out_nc


def wind_speed_from_uv(u: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Wind speed = sqrt(u^2 + v^2)."""
    return np.sqrt(np.asarray(u, float) ** 2 + np.asarray(v, float) ** 2)


def load_wind_timeseries(nc_path: str | Path, source: str = "era5"):
    """Load a wind NetCDF and return (times, lat, lon, wind[T,lat,lon] in m/s).

    Uses xarray; handles ERA5 (u10/v10) and E-OBS (fg) variable names.
    """
    import xarray as xr
    ds = xr.open_dataset(nc_path)
    if source == "era5":
        u = ds.get("u10", ds.get("10m_u_component_of_wind"))
        v = ds.get("v10", ds.get("10m_v_component_of_wind"))
        wind = np.sqrt(u.values ** 2 + v.values ** 2)
        lat = u["latitude"].values; lon = u["longitude"].values
        times = u["time"].values
    else:  # eobs / generic single wind variable
        name = "fg" if "fg" in ds else [v for v in ds.data_vars][0]
        wind = ds[name].values
        lat = ds["latitude"].values; lon = ds["longitude"].values
        times = ds["time"].values
    ds.close()
    return times, lat, lon, wind


# --------------------------------------------------------------------------- #
# ERA5 HOURLY wind for the reference year -> monthly time-integrated Vd(LAI)
# (added 05.10.2026: replaces monthly-MEAN wind, which underestimates Vd ~40 %
#  because Table A1 is convex; Vd(LAI) is evaluated per hour, then averaged)
# --------------------------------------------------------------------------- #
def hourly_wind_paths(cfg) -> list:
    """Expected monthly hourly-wind files for cfg.reference_year (12 paths)."""
    cache = Path(cfg.cache_dir)
    year = int(cfg.reference_year)
    ds_name = getattr(cfg, "era5_wind_dataset", "reanalysis-era5-single-levels")
    tag = "era5land" if "land" in ds_name else "era5"
    return [cache / (f"era5_hourly_wind_{year}_{m:02d}.nc" if tag == "era5"
                     else f"{tag}_hourly_wind_{year}_{m:02d}.nc") for m in range(1, 13)]


def download_era5_hourly_wind_year(cfg) -> list:
    """Download ERA5 hourly 10 m u/v for cfg.reference_year, one file per month.

    Files are cached as <cache_dir>/era5_hourly_wind_<year>_<mm>.nc, so an
    interrupted download resumes from the missing months.
    """
    cache = Path(cfg.cache_dir); cache.mkdir(parents=True, exist_ok=True)
    bbox = getattr(cfg, "bbox_wgs84", [59.9, 21.5, 57.3, 28.3])   # [N, W, S, E]
    year = int(cfg.reference_year)
    ds_name = getattr(cfg, "era5_wind_dataset", "reanalysis-era5-single-levels")
    tag = "era5land" if "land" in ds_name else "era5"   # ERA5-Land: 0.1 deg, land only
    files, c = [], None
    for m in range(1, 13):
        fn = hourly_wind_paths(cfg)[m - 1]
        if not fn.exists():
            if c is None:
                c = cdsapi_client(getattr(cfg, "cds_rc_path", None))
            log.info("ERA5 hourly download %s-%02d", year, m)
            req = {
                    "variable": ["10m_u_component_of_wind", "10m_v_component_of_wind"],
                    "year": str(year),
                    "month": f"{m:02d}",
                    "day": [f"{d:02d}" for d in range(1, 32)],
                    "time": [f"{h:02d}:00" for h in range(24)],
                    "area": bbox,
                    "format": "netcdf",
                }
            if tag == "era5":
                req["product_type"] = "reanalysis"
            c.retrieve(ds_name, req, str(fn))
        files.append(fn)
    return files


def _open_uv(nc_path):
    """Return (wind[T,lat,lon], lat, lon) from an ERA5 u/v NetCDF (old or new CDS)."""
    import xarray as xr
    if zipfile.is_zipfile(nc_path):
        with zipfile.ZipFile(nc_path) as archive:
            members = [name for name in archive.namelist() if name.lower().endswith(".nc")]
            if not members:
                raise ValueError(f"CDS archive contains no NetCDF file: {nc_path}")
            with tempfile.TemporaryDirectory() as temp_dir:
                extracted = Path(temp_dir) / Path(members[0]).name
                extracted.write_bytes(archive.read(members[0]))
                ds = xr.open_dataset(extracted)
                ds.load()
                ds.close()
    else:
        ds = xr.open_dataset(nc_path)
    u = ds.get("u10", ds.get("10m_u_component_of_wind"))
    v = ds.get("v10", ds.get("10m_v_component_of_wind"))
    # new CDS backend: 'valid_time'; ERA5T may add an 'expver' dimension
    for extra in [d for d in u.dims if d not in ("time", "valid_time", "latitude", "longitude")]:
        u = u.max(extra); v = v.max(extra)
    wind = np.sqrt(u.values.astype(float) ** 2 + v.values.astype(float) ** 2)
    lat = u["latitude"].values; lon = u["longitude"].values
    ds.close()
    return wind, lat, lon


def monthly_vdlai_from_hourly(files) -> tuple:
    """[12, lat, lon] monthly mean of Vd(LAI)(hourly wind), plus diagnostics.

    Returns (vdlai_m, lat, lon, diag) where diag holds per-month national means of
    wind, Vd(LAI) integrated over hours, Vd(LAI) at the daily-mean wind and Vd(LAI)
    at the monthly-mean wind (to quantify the averaging bias).
    """
    from .vd import vdlai_from_wind
    out, rows = [], []
    lat = lon = None
    for m, fn in enumerate(files, start=1):
        wind, lat, lon = _open_uv(fn)                       # [T, lat, lon]
        vd_h = np.nanmean(vdlai_from_wind(wind), axis=0)   # hourly-integrated
        T = wind.shape[0] - wind.shape[0] % 24
        daily = wind[:T].reshape(T // 24, 24, *wind.shape[1:]).mean(axis=1)
        vd_d = np.nanmean(vdlai_from_wind(daily), axis=0)  # daily-mean wind
        vd_mm = vdlai_from_wind(np.nanmean(wind, axis=0))   # monthly-mean wind
        out.append(vd_h)
        rows.append({"month": m, "wind_mean_ms": float(np.nanmean(wind)),
                     "wind_p95_ms": float(np.nanpercentile(wind, 95)),
                     "vdlai_hourly": float(np.nanmean(vd_h)),
                     "vdlai_dailymean": float(np.nanmean(vd_d)),
                     "vdlai_monthlymean": float(np.nanmean(vd_mm))})
    return np.stack(out), lat, lon, rows
