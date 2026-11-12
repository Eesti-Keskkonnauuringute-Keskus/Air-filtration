"""Configuration: dataclass + YAML loader."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

import yaml

from .constants import DEFAULT_CRS


@dataclass
class Config:
    reference_year: int = 2024
    crs: str = DEFAULT_CRS
    bbox: Optional[list] = None                      # [minx, miny, maxx, maxy] in `crs`
    analysis_resolution: int = 1000                  # metres
    approach: str = "advanced"                       # advanced | basic
    pm_fraction: str = "PM2.5"                        # PM2.5 | PM10
    temporal_resolution: str = "daily"               # hourly | daily | dekadal | monthly | annual
    concentration_source: str = "both"               # 1km | 10km | both
    wind_source: str = "era5"                        # era5 | eobs | cams
    era5_wind_dataset: str = "reanalysis-era5-single-levels"   # or reanalysis-era5-land (0.1 deg, land only)
    lai_collection: str = "clms_lai_300m"
    lai_version: str = "v2"
    deposition_days: int = 365
    wind_height_m: int = 10
    # Units + summation convention. The default pair reproduces the guidance-note
    # / 2024-assessment national total (~550 t for Estonia) and passes the
    # mass-balance check. See aggregate.py docstring before changing these.
    output_unit: str = "t_per_ha_per_yr"             # t_per_ha_per_yr | t_per_km2_per_yr
    aggregation_convention: str = "guidance"         # guidance | area_weighted
    national_total_emissions_t: Optional[float] = None  # for the mass-balance check (e.g. 4900)

    # paths
    conc_1km_path: Optional[str] = None
    conc_10km_path: Optional[str] = None
    conc_field: str = "Conc"
    clc_path: Optional[str] = None
    boundary_path: Optional[str] = None
    input_dir: str = "inputs"
    output_dir: str = "outputs"
    cache_dir: str = "cache"

    # API dataset identifiers (VERIFY current values at runtime)
    era5_dataset: str = "reanalysis-era5-single-levels"
    eobs_dataset: str = "insitu-gridded-observations-europe"
    cams_dataset: str = "cams-europe-air-quality-reanalyses"
    credentials_source: str = "env"                  # env | .cdsapirc
    # Separate credential files for the two data stores (optional). CDS = Climate
    # (ERA5/E-OBS); ADS = Atmosphere (CAMS). If null, cdsapi's default ~/.cdsapirc
    # (or CDSAPI_URL/CDSAPI_KEY env vars) is used.
    cds_rc_path: Optional[str] = None                # e.g. ~/.cdsapirc_cds  (ERA5/E-OBS)
    ads_rc_path: Optional[str] = None                # e.g. ~/.cdsapirc_ads  (CAMS)

    # offline mode (no API): local E-OBS wind NetCDF + local summer-LAI raster
    wind_local_path: Optional[str] = None            # local E-OBS 'fg' NetCDF (daily wind)
    lai_local_path: Optional[str] = None             # local summer/peak LAI raster (GeoTIFF)
    lai_base_value: float = 4.6                       # fallback constant LAI if no raster

    # monthly-consistent pipeline (run_monthly)
    concentration_provider: str = "ask"              # ask | airviro | cams
    airviro_monthly_pattern: str = "PM25_conc_{year}_{month:02d}"  # 12 files in input_dir
    lai_source: str = "phenology"                    # phenology | clms
    cams_type: str = "interim_reanalysis"            # interim_reanalysis | validated_reanalysis
    # Which CAMS product to pull when concentration_provider = cams. Both defaults
    # are AREA-SUBSETTABLE and fit the ADS cost limit (the old europe_reanalysis
    # does not). eac4_monthly = global reanalysis monthly (0.75 deg, guaranteed
    # small); europe_forecast = regional analysis (0.1 deg, subset to Estonia).
    cams_product: str = "eac4_monthly"               # eac4_monthly | europe_forecast | europe_reanalysis
    # wind_source above also accepts 'eobs_local' | 'era5_monthly' for run_monthly
    #   NB: era5_monthly is DEPRECATED - the monthly-means product averages the
    #   u/v components and underestimates wind speed (~-50 %); use era5_hourly.

    # ---- DAILY production pipeline (run_daily; 2024 report, Oct 2026) ----------
    # analysis grid (L-EST97): upper-left corner, size (cols, rows), cell 1000 m
    grid_origin: Optional[list] = None                # [x_left, y_top], e.g. [370000, 6620000]
    grid_size: Optional[list] = None                  # [ncols, nrows], e.g. [380, 250]
    conc_daily_path: Optional[str] = None             # Airviro daily-mean NetCDF (lat/lon, time)
    conc_daily_var: str = "a1d"                       # variable name in that NetCDF
    ecosystem_extent_path: Optional[str] = None       # Statistics Estonia level-2 raster (stat_EU_II.tif)
    lai_dir: Optional[str] = None                     # folder with CLMS/C3S Sentinel-3 LAI dekad NetCDFs
    lai_peak_path: Optional[str] = None               # PROBA-V summer peak LAI raster (LAI1/LAI.tif)
    lai_mode: str = "hybrid"                          # hybrid | satellite | phenology
    sensitivity_lai_modes: list = field(default_factory=lambda: ["satellite"])
    evergreen_winter_correction: bool = True
    make_figures: bool = True
    compare_10km: bool = True                         # task 1.1.2: 1 km vs 10 km concentration input
    write_shapefile: bool = True                      # 1 km grid polygons with results (.shp)

    def __post_init__(self):
        # '~' in path fields -> the user's home folder (configs stay machine-independent)
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if (name.endswith("_path") or name.endswith("_dir")) and isinstance(value, str) \
                    and value.startswith("~"):
                setattr(self, name, str(Path(value).expanduser()))
        if self.approach not in ("advanced", "basic"):
            raise ValueError("approach must be 'advanced' or 'basic'")
        if self.concentration_source not in ("1km", "10km", "both"):
            raise ValueError("concentration_source must be 1km|10km|both")
        if self.output_unit not in ("t_per_km2_per_yr", "t_per_ha_per_yr"):
            raise ValueError("output_unit invalid")
        if self.aggregation_convention not in ("guidance", "area_weighted"):
            raise ValueError("aggregation_convention must be 'guidance' or 'area_weighted'")
        if self.concentration_provider not in ("ask", "airviro", "cams"):
            raise ValueError("concentration_provider must be 'ask', 'airviro' or 'cams'")
        if self.lai_mode not in ("hybrid", "satellite", "phenology"):
            raise ValueError("lai_mode must be 'hybrid', 'satellite' or 'phenology'")
        if self.cams_product not in ("eac4_monthly", "europe_forecast", "europe_reanalysis"):
            raise ValueError("cams_product must be 'eac4_monthly', 'europe_forecast' "
                             "or 'europe_reanalysis'")

    @classmethod
    def from_yaml(cls, path: str | Path) -> "Config":
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        known = {f for f in cls.__dataclass_fields__}
        unknown = set(data) - known
        if unknown:
            raise ValueError(f"unknown config keys: {sorted(unknown)}")
        return cls(**data)

    def to_dict(self) -> dict:
        return asdict(self)

    def sources(self) -> list[str]:
        return ["1km", "10km"] if self.concentration_source == "both" else [self.concentration_source]
