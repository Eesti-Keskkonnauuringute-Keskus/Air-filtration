"""Fetch multi-temporal LAI from the Copernicus Land Monitoring Service (CLMS)
via the CDS `satellite-lai-fapar` dataset.

The CDS distributes the Copernicus Global Land LAI 10-daily product. For 2024 the
Latest product is Sentinel-3 OLCI/SLSTR 300 m, version v4_1. Access uses the same
(verified) CDS token as ERA5 - point `cds_rc_path` at .cdsapirc_cds.

The exact request below is the one the CDS download form generates (note the
non-obvious values: product_version = "v4_1", sensor = "olci_and_slstr", and NO
`satellite` field). The delivery is a ZIP of per-dekad NetCDF files.

LAI seasonality matters: because Vd is proportional to LAI and dry deposition is
year-round, a single summer LAI applied to the whole year overestimates
deciduous-type deposition ~2x. We download ALL dekads (36/yr: nominal days 10, 20
and month-end) and reduce them to a climatological monthly profile.
"""
from __future__ import annotations

from pathlib import Path
import logging

import numpy as np

log = logging.getLogger(__name__)

# Number of 10-day composites (dekads) in a year for the CLMS 300 m LAI product.
DEKADS_PER_YEAR = 36
# Nominal days per month for the 10-daily product (3rd dekad = month end).
LAI_NOMINAL_DAYS = ["10", "20", "28", "29", "30", "31"]


def download_lai_dekads(year: int, out_dir: str | Path,
                        cds_rc_path: str | Path | None = None,
                        area: list | None = None,
                        horizontal_resolution: str = "300m",
                        product_version: str = "v4_1",
                        sensor: str = "olci_and_slstr",
                        satellite=("sentinel_3",),
                        dataset: str = "satellite-lai-fapar") -> list[Path]:
    """Download CLMS satellite LAI (10-daily) for `year` from the CDS.

    Returns the extracted per-dekad NetCDF paths. `area` = [N, W, S, E] in WGS84
    subsets to a region (e.g. Estonia) to keep the download small. Requires the
    verified CDS token via `cds_rc_path`. Older years need different
    satellite/sensor/version/resolution - check the CDS dataset page and pass them
    in (e.g. 1 km VGT for pre-2014, or v3/v2 for the 1 km record).
    """
    import zipfile
    from .acquire_wind import cdsapi_client

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # cache: reuse already-extracted dekad files
    existing = sorted(out_dir.glob("*.nc"))
    if existing:
        log.info("LAI cache hit: %d dekad files in %s", len(existing), out_dir)
        return existing

    # Year-aware nominal days: the 3rd dekad falls on each month's LAST day, so
    # the valid month-end days depend on the year (Feb = 28 or 29 in a leap year
    # like 2024). Sending an invalid day (e.g. "28" in a leap year) makes the CDS
    # reject the whole request, so build the set from the calendar.
    import calendar
    month_ends = sorted({calendar.monthrange(int(year), m)[1] for m in range(1, 13)})
    nominal_days = ["10", "20"] + [f"{d:02d}" for d in month_ends]   # e.g. 2024 -> 10,20,29,30,31
    request = {
        "variable": ["lai"],
        "satellite": list(satellite),           # e.g. ["sentinel_3"]
        "sensor": sensor,                       # single string, e.g. olci_and_slstr
        "horizontal_resolution": [horizontal_resolution],
        "product_version": [product_version],   # e.g. v4_1 (NOT "V4.1")
        "year": [str(year)],
        "month": [f"{m:02d}" for m in range(1, 13)],
        "nominal_day": nominal_days,
    }
    if area:
        request["area"] = list(area)            # [N, W, S, E]

    zip_path = out_dir / f"{dataset}_{year}.zip"
    if not zip_path.exists():
        log.info("CDS download %s %s (10-daily LAI, res=%s, ver=%s, area=%s)",
                 dataset, year, horizontal_resolution, product_version, area)
        c = cdsapi_client(cds_rc_path)
        try:
            c.retrieve(dataset, request, str(zip_path))
        except Exception as e:
            raise RuntimeError(
                f"CLMS LAI download failed: {e}\nCheck the CDS token "
                "(.cdsapirc_cds), that you accepted BOTH licences on the "
                f"{dataset} page (Copernicus Global Land product licence + "
                "CC-BY), and that the satellite/sensor/version/resolution match "
                f"the year ({year} -> Sentinel-3 olci_and_slstr 300m v4_1)."
            ) from e

    # the CDS delivers a ZIP of per-dekad NetCDF files (sometimes a single .nc)
    try:
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(out_dir)
    except zipfile.BadZipFile:
        single = out_dir / f"{dataset}_{year}.nc"
        zip_path.replace(single)
        log.info("LAI delivery was a single NetCDF (not a zip)")
        return [single]

    paths = sorted(p for p in out_dir.glob("*.nc"))
    if not paths:
        raise RuntimeError(
            f"No .nc files found after extracting {zip_path}. Inspect the archive "
            "contents and adjust the extractor."
        )
    log.info("extracted %d LAI dekad files from %s", len(paths), zip_path.name)
    return paths


def _date_from_name(path) -> "np.datetime64":
    """Parse a YYYYMMDD date from a CLMS LAI filename (fallback if no time coord)."""
    import re, datetime
    m = re.search(r"(20\d{6})", Path(path).name)
    if m:
        return np.datetime64(datetime.datetime.strptime(m.group(1), "%Y%m%d"))
    return np.datetime64("NaT")


def load_lai_stack(nc_paths: list[str | Path], var: str = "LAI"):
    """Load a stack of LAI dekad files into (times, lat, lon, lai[T,lat,lon]).

    Opens each file eagerly with xr.open_dataset (NO dask / open_mfdataset, so no
    dask dependency) and stacks them in time order. CLMS LAI is stored with a
    scale factor that xarray applies automatically (mask_and_scale=True). Physical
    LAI is 0..~7 (m2/m2); flag digital numbers scale above that, so values outside
    [0, 7.5] are set to NaN.
    """
    import xarray as xr
    arrs, times = [], []
    lat = lon = None
    for p in [str(x) for x in nc_paths]:
        ds = xr.open_dataset(p)                       # eager -> plain numpy, no dask
        cands = [v for v in ds.data_vars if v == var] or \
                [v for v in ds.data_vars if "lai" in v.lower()]
        da = ds[cands[0]] if cands else ds[list(ds.data_vars)[0]]
        if lat is None:
            lat = (da["lat"].values if "lat" in da.coords else da["latitude"].values)
            lon = (da["lon"].values if "lon" in da.coords else da["longitude"].values)
        tval = (np.atleast_1d(da["time"].values)[0] if "time" in da.coords
                else _date_from_name(p))
        arr = np.asarray(da.squeeze().values, dtype="float32")
        arr = np.where((arr >= 0) & (arr <= 7.5), arr, np.nan)   # drop flag values
        arrs.append(arr); times.append(tval)
        ds.close()
    order = np.argsort(np.array(times))
    times = np.array(times)[order]
    stack = np.stack([arrs[i] for i in order]).astype("float32")
    return times, lat, lon, stack


def climatological_monthly_profile(lai_stack: np.ndarray, months: np.ndarray) -> np.ndarray:
    """Reduce a dekadal LAI stack to 12 monthly means [12, ny, nx]."""
    out = np.full((12,) + lai_stack.shape[1:], np.nan, dtype="float32")
    for m in range(1, 13):
        sel = months == m
        if sel.any():
            out[m - 1] = np.nanmean(lai_stack[sel], axis=0)
    return out


# --------------------------------------------------------------------------- #
# PROBA-V summer peak LAI (input of the 'hybrid' LAI mode)
# --------------------------------------------------------------------------- #
# Grid of the peak-LAI raster used for the 2024 report (data/LAI_peak_PROBAV_20190630.tif):
# L-EST97, 548 x 360 cells of ~795 x 793 m (as produced in 2023 with ArcGIS).
PEAK_LAI_GRID = dict(crs="EPSG:3301", width=548, height=360,
                     transform=(794.9512688298905, 0.0, 350365.9264235877,
                                0.0, -792.8609742212705, 6637974.931917285))
PEAK_LAI_AREA = dict(lat=(60.5, 56.8), lon=(20.5, 29.0))   # subset of the global file


def peak_lai_from_clms(nc_paths, out_tif, var: str = "LAI") -> Path:
    """Build the summer peak LAI GeoTIFF from Copernicus Global Land LAI 1 km V2
    (PROBA-V, GEOV2) 10-daily NetCDF files.

    The 2024 report used the dekad 30.06.2019
    (c_gls_LAI-RT6_201906300000_GLOBE_PROBAV_V2.0.1.nc). Download it from the
    CLMS dataset "Leaf Area Index 1999-2020 (raster 1 km), global, 10-daily -
    version 2" (https://land.copernicus.eu/en/products/vegetation/leaf-area-index-v2-0-1km,
    also on the Copernicus Data Space Ecosystem). With several files the
    per-pixel maximum is taken. The values are resampled (nearest neighbour) to
    PEAK_LAI_GRID; 0 = no data. The result reproduces the raster of the report
    for ~94 % of the pixels exactly (the original was resampled in ArcGIS).
    """
    import xarray as xr
    import rasterio
    from rasterio.transform import Affine, from_origin
    from rasterio.warp import reproject, Resampling

    if isinstance(nc_paths, (str, Path)):
        nc_paths = [nc_paths]
    stack = []
    for p in nc_paths:
        ds = xr.open_dataset(p)
        da = ds[var].sel(lat=slice(*PEAK_LAI_AREA["lat"]), lon=slice(*PEAK_LAI_AREA["lon"]))
        if "time" in da.dims:
            da = da.isel(time=0)
        a = np.asarray(da.values, dtype="float32")
        a = np.where((a >= 0) & (a <= 7.5), a, np.nan)          # drop flag values
        lat, lon = da["lat"].values, da["lon"].values
        ds.close()
        stack.append(a)
    src = np.nanmax(np.stack(stack), 0) if len(stack) > 1 else stack[0]
    d = float(abs(lat[1] - lat[0]))
    src_t = from_origin(float(lon[0]) - d / 2, float(lat[0]) + d / 2, d, d)
    g = PEAK_LAI_GRID
    dst_t = Affine(*g["transform"])
    out = np.full((g["height"], g["width"]), np.nan, np.float32)
    reproject(src, out, src_transform=src_t, src_crs="EPSG:4326", dst_transform=dst_t,
              dst_crs=g["crs"], resampling=Resampling.nearest, src_nodata=np.nan, dst_nodata=np.nan)
    out = np.nan_to_num(out, nan=0.0)
    out_tif = Path(out_tif); out_tif.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(out_tif, "w", driver="GTiff", width=g["width"], height=g["height"], count=1,
                       dtype="float32", crs=g["crs"], transform=dst_t, nodata=0.0,
                       compress="deflate") as dst:
        dst.write(out, 1)
        dst.update_tags(source=", ".join(Path(p).name for p in nc_paths),
                        product="Copernicus Global Land LAI 1km V2 (PROBA-V, GEOV2)")
    log.info("peak LAI written: %s (mean %.2f over vegetated cells)", out_tif, out[out > 0].mean())
    return out_tif
