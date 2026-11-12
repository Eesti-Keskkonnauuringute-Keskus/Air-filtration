"""Write outputs: deposition GeoTIFF/shapefile, reporting tables, run metadata."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


def write_geotiff(deposition: np.ndarray, grid, out_path: str | Path, field_desc: str) -> Path:
    import rasterio
    out_path = Path(out_path)
    with rasterio.open(
        out_path, "w", driver="GTiff",
        height=grid.height, width=grid.width, count=1,
        dtype="float32", crs=grid.crs, transform=grid.transform, nodata=np.nan,
    ) as ds:
        ds.write(deposition.astype("float32"), 1)
        ds.set_band_description(1, field_desc)
    return out_path


def write_shapefile(deposition: np.ndarray, grid, out_path: str | Path, field: str = "dep") -> Path:
    """Vectorise the deposition grid to a polygon shapefile (one polygon per cell)."""
    import geopandas as gpd
    from shapely.geometry import box
    out_path = Path(out_path)
    tr = grid.transform
    polys, vals = [], []
    for j in range(grid.height):
        for i in range(grid.width):
            v = deposition[j, i]
            if not np.isfinite(v):
                continue
            x0, y0 = tr * (i, j)
            x1, y1 = tr * (i + 1, j + 1)
            polys.append(box(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)))
            vals.append(float(v))
    gdf = gpd.GeoDataFrame({field: vals}, geometry=polys, crs=grid.crs)
    gdf.to_file(out_path)
    return out_path


def write_supply_table(df: pd.DataFrame, metadata: dict, out_xlsx: str | Path) -> Path:
    out_xlsx = Path(out_xlsx)
    with pd.ExcelWriter(out_xlsx, engine="openpyxl") as xw:
        df.to_excel(xw, sheet_name="supply_by_type", index=False)
        pd.DataFrame(list(metadata.items()), columns=["field", "value"]).to_excel(
            xw, sheet_name="reporting_metadata", index=False
        )
    df.to_csv(out_xlsx.with_suffix(".csv"), index=False)
    return out_xlsx


def write_metadata(cfg, extra: dict, out_json: str | Path) -> Path:
    out_json = Path(out_json)
    payload = {"config": cfg.to_dict(), **extra}
    with open(out_json, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=str)
    return out_json
