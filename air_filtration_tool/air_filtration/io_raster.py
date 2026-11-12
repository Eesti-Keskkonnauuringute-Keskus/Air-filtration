"""Raster / vector IO and harmonisation helpers (rasterio, rioxarray, geopandas).

These wrap the common operations: load a concentration field (shapefile grid or
GeoTIFF) onto a regular analysis grid, reproject/resample auxiliary layers onto
that same grid, and clip to the accounting boundary.

The functions are intentionally dependency-light at import time so the pure
scientific core (vd, deposition) and its tests do not require GDAL to be present.
Heavy libraries are imported lazily inside each function.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np


@dataclass
class Grid:
    """A regular analysis grid definition."""
    transform: object          # affine.Affine
    width: int
    height: int
    crs: str

    @property
    def shape(self):
        return (self.height, self.width)


def load_concentration(path: str | Path, field: str, crs: str, resolution: int) -> tuple[np.ndarray, Grid]:
    """Load a PM2.5 concentration field to a regular grid.

    Accepts a polygon-grid shapefile (rasterised on `field`) or a GeoTIFF.
    Returns (conc[ny,nx] float with NaN nodata, Grid).
    """
    import rasterio
    from rasterio import features
    from rasterio.transform import from_bounds
    import geopandas as gpd

    path = Path(path)
    if path.suffix.lower() in (".tif", ".tiff"):
        with rasterio.open(path) as ds:
            arr = ds.read(1, masked=True).filled(np.nan).astype(float)
            grid = Grid(ds.transform, ds.width, ds.height, str(ds.crs))
        return arr, grid

    gdf = gpd.read_file(path).to_crs(crs)
    minx, miny, maxx, maxy = gdf.total_bounds
    width = int(round((maxx - minx) / resolution))
    height = int(round((maxy - miny) / resolution))
    transform = from_bounds(minx, miny, maxx, maxy, width, height)
    shapes = ((geom, float(val)) for geom, val in zip(gdf.geometry, gdf[field]))
    arr = features.rasterize(
        shapes, out_shape=(height, width), transform=transform,
        fill=np.nan, dtype="float64", all_touched=False,
    )
    return arr, Grid(transform, width, height, crs)


def reproject_to_grid(src_path: str | Path, grid: Grid, resampling: str = "bilinear",
                      src_crs_fallback: str | None = None, src_nodata: float | None = None) -> np.ndarray:
    """Reproject/resample a raster (GeoTIFF/NetCDF band) onto `grid`.

    If the source lacks an embedded CRS (e.g. a GeoTIFF georeferenced only by a
    world file), `src_crs_fallback` (default: the grid CRS) is assumed. Source
    nodata is masked to NaN.
    """
    import rasterio
    from rasterio.warp import reproject, Resampling
    rs = getattr(Resampling, resampling)
    dst = np.full(grid.shape, np.nan, dtype="float64")
    with rasterio.open(src_path) as ds:
        src_crs = ds.crs or src_crs_fallback or grid.crs
        arr = ds.read(1).astype("float64")
        nod = src_nodata if src_nodata is not None else ds.nodata
        if nod is not None:
            arr[arr == nod] = np.nan
        reproject(
            source=arr, destination=dst,
            src_transform=ds.transform, src_crs=src_crs,
            dst_transform=grid.transform, dst_crs=grid.crs,
            src_nodata=np.nan, dst_nodata=np.nan,
            resampling=rs,
        )
    return dst


def rasterize_clc(clc_path: str | Path, grid: Grid) -> np.ndarray:
    """Return the CLC code grid (majority/nearest) aligned to `grid`."""
    import rasterio
    from rasterio.warp import reproject, Resampling
    dst = np.zeros(grid.shape, dtype="int32")
    with rasterio.open(clc_path) as ds:
        reproject(
            source=rasterio.band(ds, 1), destination=dst,
            src_transform=ds.transform, src_crs=ds.crs or grid.crs,
            dst_transform=grid.transform, dst_crs=grid.crs,
            resampling=Resampling.nearest,
        )
    return dst


def boundary_mask(boundary_path: str | Path, grid: Grid) -> np.ndarray:
    """Boolean mask (True = inside the accounting area) on `grid`."""
    import geopandas as gpd
    from rasterio import features
    gdf = gpd.read_file(boundary_path).to_crs(grid.crs)
    geom = [g for g in gdf.geometry]
    mask = features.geometry_mask(
        geom, out_shape=grid.shape, transform=grid.transform, invert=True
    )
    return mask


def aggregate_1km_to_block(conc_1km: np.ndarray, block: int = 10) -> np.ndarray:
    """Block-mean aggregate a fine grid to coarser cells (e.g. 1 km -> 10 km),
    then broadcast back to the fine grid. Used to derive a 10 km concentration
    from the 1 km field for the resolution comparison."""
    ny, nx = conc_1km.shape
    out = conc_1km.copy()
    for j in range(0, ny, block):
        for i in range(0, nx, block):
            sub = conc_1km[j:j + block, i:i + block]
            m = np.nanmean(sub)
            out[j:j + block, i:i + block] = m
    return out
