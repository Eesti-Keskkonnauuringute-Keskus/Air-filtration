"""Input builders for the DAILY production pipeline (run_daily).

All functions return arrays on the 1 km analysis grid (L-EST97):
  * daily PM2.5 concentration from the Airviro daily-mean NetCDF
  * daily Vd(LAI) from ERA5-Land HOURLY wind (Table A1 applied to every hour)
  * daily LAI (Sentinel-3 dekads interpolated; evergreen winter correction;
    hybrid rescaling to the PROBA-V summer peak)
  * level-2 ecosystem area fractions per 1 km cell (Statistics Estonia map)

These reproduce exactly the calculation used for the 2024 report
(EKUK, October 2026): main estimate = 'hybrid' LAI, sensitivity = 'satellite'.
"""
from __future__ import annotations

import glob
import logging
import warnings
from pathlib import Path

import warnings
# all-NaN cells (sea, outside Estonia) are expected; their numpy warnings are noise
warnings.filterwarnings("ignore", message="Mean of empty slice", category=RuntimeWarning)
warnings.filterwarnings("ignore", message="All-NaN slice encountered", category=RuntimeWarning)
import numpy as np

from .io_raster import Grid
from .constants import STAT_L2_CLASSES, STAT_EVERGREEN_WEIGHTS, PHENOLOGY_PROFILES

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------- grid
def grid_from_config(cfg) -> Grid:
    from rasterio.transform import from_origin
    x0, y0 = cfg.grid_origin
    nx, ny = cfg.grid_size
    r = cfg.analysis_resolution
    return Grid(from_origin(x0, y0, r, r), int(nx), int(ny), cfg.crs)


def year_days(year: int) -> np.ndarray:
    return np.arange(np.datetime64(f"{year}-01-01"), np.datetime64(f"{year + 1}-01-01"))


def cell_centres(grid: Grid):
    j, i = np.mgrid[0:grid.height, 0:grid.width]
    return grid.transform * (i + 0.5, j + 0.5)


# ------------------------------------------------------------------ concentration
def airviro_daily(nc_path, var: str, grid: Grid) -> np.ndarray:
    """[T, ny, nx] daily PM2.5 (ug/m3) from a regular lat/lon NetCDF, area-average
    resampled to the analysis grid. Time steps are taken in file order (the 2024
    file has 366 days starting 2024-01-01 00:00 local time)."""
    import xarray as xr
    from rasterio.warp import reproject, Resampling
    from rasterio.transform import from_origin
    ds = xr.open_dataset(nc_path, decode_times=False)
    lat = ds["latitude"].values.astype(float); lon = ds["longitude"].values.astype(float)
    a = ds[var].values
    ds.close()
    dlat = abs(np.diff(lat).mean()); dlon = np.diff(lon).mean()
    asc = lat[0] < lat[-1]
    top = (lat[-1] if asc else lat[0]) + dlat / 2
    src_t = from_origin(lon[0] - dlon / 2, top, dlon, dlat)
    out = np.full((a.shape[0],) + grid.shape, np.nan, np.float32)
    for k in range(a.shape[0]):
        src = (a[k][::-1] if asc else a[k]).astype(np.float32)
        reproject(src, out[k], src_transform=src_t, src_crs="EPSG:4326",
                  dst_transform=grid.transform, dst_crs=grid.crs,
                  resampling=Resampling.average, src_nodata=np.nan, dst_nodata=np.nan)
    log.info("Airviro daily concentration: %d days, mean %.2f ug/m3", a.shape[0], np.nanmean(out))
    return out


# ---------------------------------------------------------------------- wind / Vd
def daily_vdlai_era5(files, grid: Grid):
    """Daily Vd(LAI) [T, ny, nx] (cm/s) and daily mean wind (m/s) from hourly ERA5(-Land)
    files. Vd(LAI) is evaluated per HOUR (Table A1) and averaged per day. Each grid
    cell takes the nearest ERA5 point that has data (ERA5-Land is land-only)."""
    from scipy.spatial import cKDTree
    from pyproj import Transformer
    from .acquire_wind import _open_uv
    from .vd import vdlai_from_wind
    vd, wd = [], []
    lat = lon = None
    for fn in files:
        w, lat, lon = _open_uv(fn)
        n = w.shape[0] // 24
        w = w[:n * 24].reshape(n, 24, *w.shape[1:])
        with warnings.catch_warnings():   # ERA5-Land sea points are all-NaN -> harmless
            warnings.simplefilter("ignore", RuntimeWarning)
            vd.append(vdlai_from_wind(w).mean(1)); wd.append(np.nanmean(w, 1))
    vd = np.concatenate(vd); wd = np.concatenate(wd)
    valid = ~np.isnan(wd).any(0)
    LA, LO = np.meshgrid(lat, lon, indexing="ij")
    px, py = Transformer.from_crs("EPSG:4326", grid.crs, always_xy=True).transform(LO[valid], LA[valid])
    xs, ys = cell_centres(grid)
    _, k = cKDTree(np.c_[px, py]).query(np.c_[xs.ravel(), ys.ravel()])
    vi = np.argwhere(valid)
    a = vi[k, 0].reshape(grid.shape); b = vi[k, 1].reshape(grid.shape)
    log.info("wind: %d days from %d files, nearest-valid mapping", vd.shape[0], len(files))
    return vd[:, a, b].astype(np.float32), wd[:, a, b].astype(np.float32)


def era5_hourly_files(cfg) -> list:
    """Cached hourly files for the reference year (downloads missing months)."""
    from .acquire_wind import download_era5_hourly_wind_year
    return [Path(f) for f in download_era5_hourly_wind_year(cfg)]


# --------------------------------------------------------------------- ecosystems
def ecosystem_fractions(extent_path, grid: Grid, n_classes: int = 30, chunk_rows: int = 500) -> np.ndarray:
    """Area [ny, nx, n_classes] (m2) of each level-2 class in every 1 km cell,
    counted from the 10 m extent raster (pixel centre -> cell)."""
    import rasterio
    from rasterio.windows import Window
    H, W = grid.shape; gt = grid.transform
    counts = np.zeros((H * W, n_classes + 1), np.int64)
    with rasterio.open(extent_path) as src:
        st = src.transform
        col = np.floor((st.c + (np.arange(src.width) + 0.5) * st.a - gt.c) / gt.a).astype(int)
        for r0 in range(0, src.height, chunk_rows):
            n = min(chunk_rows, src.height - r0)
            a = src.read(1, window=Window(0, r0, src.width, n)).astype(np.int16)
            row = np.floor((st.f + (np.arange(r0, r0 + n) + 0.5) * st.e - gt.f) / gt.e).astype(int)
            R = np.broadcast_to(row[:, None], a.shape); C = np.broadcast_to(col[None, :], a.shape)
            ok = (a >= 1) & (a <= n_classes) & (R >= 0) & (R < H) & (C >= 0) & (C < W)
            idx = (R[ok] * W + C[ok]) * (n_classes + 1) + a[ok]
            counts += np.bincount(idx, minlength=H * W * (n_classes + 1)).reshape(H * W, n_classes + 1)
        pix_area = abs(st.a * st.e)
    return (counts[:, 1:].reshape(H, W, n_classes) * pix_area).astype(np.float64)


def evergreen_share(frac: np.ndarray) -> np.ndarray:
    fe = np.zeros(frac.shape[:2])
    for code, w in STAT_EVERGREEN_WEIGHTS.items():
        fe += w * frac[..., code - 1]
    return fe


def class_phenology_daily(days: np.ndarray) -> np.ndarray:
    """[30, T] fraction-of-peak LAI per level-2 class per day (monthly profile)."""
    month = np.array([int(str(d)[5:7]) for d in days]) - 1
    out = np.zeros((len(STAT_L2_CLASSES), len(days)))
    for k, (_, _, _, blend) in enumerate(STAT_L2_CLASSES):
        prof = sum(w * np.asarray(PHENOLOGY_PROFILES[c]) for c, w in blend.items())
        out[k] = prof[month]
    return out


# ---------------------------------------------------------------------------- LAI
def satellite_lai_daily(lai_dir, grid: Grid, year: int) -> np.ndarray:
    """Sentinel-3 LAI dekads (CLMS/C3S, 300 m) -> area-average on grid -> linear
    interpolation to every day of `year`. [T, ny, nx]."""
    from rasterio.warp import reproject, Resampling
    from rasterio.transform import from_origin
    from .acquire_lai import load_lai_stack
    paths = sorted(glob.glob(str(Path(lai_dir) / "*.nc")))
    t, lat, lon, st = load_lai_stack(paths)
    dla = abs(np.diff(lat).mean()); dlo = np.diff(lon).mean()
    desc = lat[0] > lat[-1]
    src_t = from_origin(lon[0] - dlo / 2, (lat[0] if desc else lat[-1]) + dla / 2, dlo, dla)
    G = np.full((len(t),) + grid.shape, np.nan, np.float32)
    for k in range(len(t)):
        s = st[k] if desc else st[k][::-1]
        reproject(s, G[k], src_transform=src_t, src_crs="EPSG:4326", dst_transform=grid.transform,
                  dst_crs=grid.crs, resampling=Resampling.average, src_nodata=np.nan, dst_nodata=np.nan)
    days = year_days(year)
    x = (np.array(t).astype("datetime64[D]") - days[0]).astype(int); xd = np.arange(len(days))
    idx = np.clip(np.searchsorted(x, xd) - 1, 0, len(x) - 2)
    w = np.clip((xd - x[idx]) / (x[idx + 1] - x[idx]), 0, 1)
    LS = (1 - w)[:, None, None] * G[idx] + w[:, None, None] * G[idx + 1]
    LS = np.where(np.isnan(LS), np.where(np.isnan(G[idx]), G[idx + 1], G[idx]), LS)
    log.info("satellite LAI: %d dekads -> %d days", len(t), len(days))
    return LS.astype(np.float32)


def evergreen_correction(LS: np.ndarray, fe: np.ndarray, days: np.ndarray) -> np.ndarray:
    """Winter LAI of the evergreen share may not fall below the evergreen
    phenology profile x the cell's annual LAI maximum."""
    month = np.array([int(str(d)[5:7]) for d in days]) - 1
    peak = np.nanmax(LS, 0)
    pe = np.asarray(PHENOLOGY_PROFILES["evergreen"])[month]
    return ((1 - fe)[None] * LS + fe[None] * np.maximum(LS, pe[:, None, None] * peak[None])).astype(np.float32)


def hybrid_lai(LSc: np.ndarray, peak_raster: np.ndarray) -> np.ndarray:
    """Sentinel-3 seasonal course (normalised to its annual max per cell) x PROBA-V
    summer peak LAI. Cells with an annual max <= 0.2 are treated as non-vegetated."""
    peak = np.nanmax(LSc, 0)
    with np.errstate(invalid="ignore", divide="ignore"):
        sh = np.where(peak[None] > 0.2, LSc / np.maximum(peak[None], 1e-3), np.nan)
    return (np.minimum(sh, 1) * np.nan_to_num(peak_raster)[None]).astype(np.float32)
