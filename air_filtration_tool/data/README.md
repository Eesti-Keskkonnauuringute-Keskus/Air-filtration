# Data shipped with the tool

## `LAI_peak_PROBAV_20190630.tif` — summer peak LAI

Input of the main estimate (`lai_mode: hybrid`), the same raster as used for the 2024 report.

* **Source:** Copernicus Land Monitoring Service, *Leaf Area Index 1999–2020 (raster 1 km),
  global, 10-daily – version 2* (GEOV2, PROBA-V), dekad 30.06.2019, file
  `c_gls_LAI-RT6_201906300000_GLOBE_PROBAV_V2.0.1.nc`.
  DOI 10.2909/d5fdc595-2e03-4cbe-a39e-5f006f9cef07,
  <https://land.copernicus.eu/en/products/vegetation/leaf-area-index-v2-0-1km>.
* **Processing:** subset to Estonia and resampled (nearest neighbour) to L-EST97
  (EPSG:3301), 548 × 360 cells of ~795 m; 0 = no data. The original was produced in ArcGIS
  (2023).
* **Rebuild from the source file** (download it from the CLMS dataset page or the
  Copernicus Data Space Ecosystem; a free account is required):
  ```bat
  python -m air_filtration peak-lai --source c_gls_LAI-RT6_201906300000_GLOBE_PROBAV_V2.0.1.nc --out data\LAI_peak_rebuilt.tif
  ```
  The rebuilt raster is identical in ~94 % of the cells; with it the 2024 main estimate is
  206.3 t instead of 206.4 t (−0.05 %).
* **Licence:** Copernicus data, free and open access
  (Regulation (EU) No 1159/2013 and (EU) 2021/696). Attribution: *"Generated using Copernicus
  Land Monitoring Service information 2019"*.

## `maakond_20230601.*` — county boundaries

Defines the accounting area (deposition over the open sea and the parts of Lake Peipsi and
Võrtsjärv outside the counties is excluded).

* **Source:** Maa- ja Ruumiamet (Estonian Land and Spatial Development Board),
  administrative and settlement division, counties, state of 01.06.2023,
  <https://geoportaal.maaamet.ee/est/Ruumiandmed/Haldus-ja-asustusjaotus-p119.html>.
  Any later version can be used (`boundary_path` in the config).
* **Licence:** Maa- ja Ruumiamet open data licence (free use with attribution).
