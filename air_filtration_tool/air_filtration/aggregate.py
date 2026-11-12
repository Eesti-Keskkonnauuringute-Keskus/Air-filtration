"""Aggregate the deposition field by EU ecosystem type level 1 (via CLC).

Units / summation convention (IMPORTANT - this is what reproduces the guidance
note result, ~550 t for Estonia):

The guidance note Eq. 3 computes per-cell deposition as
    dep = Vd[cm/s] x C[ug/m3] x 3.1536e-3        (formally tonnes/HECTARE/year)
and states the national total as the SUM of those per-cell values ("tonnes/year").
That is the convention the 2024 assessment used and it lands within the physical
mass-balance ceiling (national deposition must be a fraction of national PM2.5
emissions). This module therefore defaults to:

    output_unit = 't_per_ha_per_yr'  (factor 3.1536e-3)
    convention  = 'guidance'         (national total = sum of per-cell values)

A dimensionally strict 'area_weighted' convention (tonnes = dep x cell area) is
also provided, but note it multiplies the total by ~100 for 1 km2 cells and then
breaches the emissions ceiling - use it only after validating against the
mass-balance check below.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from .constants import ECOSYSTEM_TYPES_L1, CLC_TO_ECOSYSTEM_L1

log = logging.getLogger(__name__)


def clc_to_ecosystem_index(clc_grid: np.ndarray) -> np.ndarray:
    """Map a CLC grid to ecosystem-type indices (0..11); -1 = unmapped.

    Accepts either 3-digit CLC codes (111..523) or the Copernicus 100 m raster's
    GRID_CODE (1..44). The Copernicus CLC raster stores GRID_CODE, not the 3-digit
    codes, so those are translated first: the CLC legend orders GRID_CODE 1..44 as
    exactly the sorted 3-digit codes 111..523.
    """
    clc_grid = np.asarray(clc_grid)
    out = np.full(clc_grid.shape, -1, dtype=np.int16)
    clc_codes = set(CLC_TO_ECOSYSTEM_L1)              # the 44 valid 3-digit codes
    present = set(int(v) for v in np.unique(clc_grid))
    if present.isdisjoint(clc_codes):                # no 3-digit codes -> GRID_CODE raster
        codes_sorted = sorted(clc_codes)             # 111..523 in legend order
        translated = np.zeros_like(clc_grid)
        for g, code in enumerate(codes_sorted, start=1):   # GRID_CODE g -> 3-digit code
            translated[clc_grid == g] = code
        clc_grid = translated
    for code, idx in CLC_TO_ECOSYSTEM_L1.items():
        out[clc_grid == code] = idx
    return out


def _area_factor(convention: str, output_unit: str, cell_area_km2: float) -> float:
    if convention == "guidance":
        # sum per-cell values directly (guidance note / 2024 assessment convention)
        return 1.0
    if convention == "area_weighted":
        if output_unit == "t_per_km2_per_yr":
            return cell_area_km2
        if output_unit == "t_per_ha_per_yr":
            return cell_area_km2 * 100.0
    raise ValueError(f"bad convention/output_unit: {convention}/{output_unit}")


def supply_by_ecosystem_type(
    deposition: np.ndarray,
    ecosystem_index: np.ndarray,
    cell_area_km2: float,
    output_unit: str = "t_per_ha_per_yr",
    convention: str = "guidance",
) -> pd.DataFrame:
    """Sum deposition by ecosystem type -> tonnes PM per year.

    See the module docstring for the units/summation convention. The default
    (t_per_ha_per_yr + guidance) reproduces the guidance-note / 2024-assessment
    national total.
    """
    area_factor = _area_factor(convention, output_unit, cell_area_km2)
    rows = []
    for idx, name in enumerate(ECOSYSTEM_TYPES_L1):
        sel = ecosystem_index == idx
        tonnes = float(np.nansum(deposition[sel]) * area_factor)
        rows.append({"ecosystem_type_l1": name, "air_filtration_t_per_yr": tonnes})
    df = pd.DataFrame(rows)
    df.loc[len(df)] = {
        "ecosystem_type_l1": "NATIONAL TOTAL",
        "air_filtration_t_per_yr": df["air_filtration_t_per_yr"].sum(),
    }
    return df


def mass_balance_check(national_total_t: float, emissions_t: float | None) -> dict:
    """Sanity gate: national dry deposition cannot exceed national PM2.5 in air.

    A physically plausible air-filtration total is a modest fraction of national
    PM2.5 emissions (Estonia 2022: ~552 t is ~11% of ~4900 t). Logs a warning if
    the total approaches, and an error if it breaches, the emissions ceiling.
    """
    if not emissions_t:
        return {"national_total_t": national_total_t, "emissions_t": None, "status": "unchecked"}
    ratio = national_total_t / emissions_t
    if ratio > 1.0:
        status = "IMPOSSIBLE (> national emissions - check units/summation convention)"
        log.error("mass balance: total %.0f t = %.0f%% of emissions %.0f t - %s",
                  national_total_t, 100 * ratio, emissions_t, status)
    elif ratio > 0.5:
        status = "implausibly high (> 50% of emissions)"
        log.warning("mass balance: total %.0f t = %.0f%% of emissions - %s",
                    national_total_t, 100 * ratio, status)
    else:
        status = "plausible"
        log.info("mass balance: total %.0f t = %.1f%% of national emissions - %s",
                 national_total_t, 100 * ratio, status)
    return {"national_total_t": national_total_t, "emissions_t": emissions_t,
            "ratio_of_emissions": ratio, "status": status}


def reporting_metadata(cfg) -> dict:
    """The extra fields the guidance note requires alongside the supply table."""
    return {
        "size_grouping": cfg.pm_fraction,
        "vd_approach": (
            "modelled from LAI and wind speed (advanced approach)"
            if cfg.approach == "advanced"
            else "default Vd by ecosystem type (basic approach, Annex 2)"
        ),
        "temporal_resolution": cfg.temporal_resolution,
        "wind_source": cfg.wind_source,
        "reference_year": cfg.reference_year,
        "output_unit": cfg.output_unit,
        "summation_convention": getattr(cfg, "aggregation_convention", "guidance"),
    }
