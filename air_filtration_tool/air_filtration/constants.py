"""
Physical constants, lookup tables and classification cross-walks for the
air-filtration ecosystem-service model.

All values follow the Eurostat ENV_EA Task Force
"Guidance note for accounting for the air filtration ecosystem service in the EU".
"""
from __future__ import annotations

import numpy as np

# ---------------------------------------------------------------------------
# Table A1 (guidance note, Annex 1): deposition velocity per unit LAI for PM2.5
# as a NON-LINEAR function of wind speed. Values are NET (resuspension already
# subtracted), in cm/s. Interpolate linearly; clamp outside [0, 13] m/s.
# ---------------------------------------------------------------------------
TABLE_A1_WIND_MS = np.array(
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13], dtype=float
)
TABLE_A1_VDLAI_CMS = np.array(
    [0.000, 0.030, 0.087, 0.143, 0.160, 0.176, 0.182,
     0.504, 0.819, 0.810, 1.836, 1.772, 1.688, 1.625],
    dtype=float,
)

# ---------------------------------------------------------------------------
# Unit conversion for the deposition integral.
#
#   deposition = sum_t ( Vd_t[cm/s] * C[ug/m3] * dt[s] ) * UNIT_FACTOR
#
# Derivation (cm/s * ug/m3 * s):
#   cm/m3 = 1e-2 /m2  ; ug -> t = 1e-12 ; per m2 -> per km2 = 1e6 ; per ha = 1e4
#   t/km2 : 1e-2 * 1e-12 * 1e6 = 1e-8  per second
#   t/ha  : 1e-2 * 1e-12 * 1e4 = 1e-10 per second
#
# NOTE / PITFALL: the guidance note Eq. 3 factor 3.1536e-3 is the ANNUAL factor
# for tonnes/HECTARE/year, NOT tonnes/km2/year. For tonnes/km2/year the annual
# factor is 0.31536 ( = SECONDS_PER_YEAR * 1e-8 ). Always validate the national
# total against a known benchmark and keep the output unit explicit.
# ---------------------------------------------------------------------------
SECONDS_PER_YEAR = 365.0 * 24.0 * 3600.0  # 31_536_000  (dry deposition assumed 365 d/yr)

UNIT_FACTOR_PER_SECOND = {
    "t_per_km2_per_yr": 1e-8,
    "t_per_ha_per_yr": 1e-10,
}
# Convenience annual factors (full-year, constant Vd*C):
ANNUAL_FACTOR = {
    "t_per_km2_per_yr": SECONDS_PER_YEAR * UNIT_FACTOR_PER_SECOND["t_per_km2_per_yr"],  # 0.31536
    "t_per_ha_per_yr": SECONDS_PER_YEAR * UNIT_FACTOR_PER_SECOND["t_per_ha_per_yr"],    # 3.1536e-3
}

# ---------------------------------------------------------------------------
# EU ecosystem typology - level 1 (MAES), Eurostat reporting order.
# ---------------------------------------------------------------------------
ECOSYSTEM_TYPES_L1 = [
    "Settlements and other artificial areas",
    "Cropland",
    "Grassland",
    "Forest and woodland",
    "Heathland and shrub",
    "Sparsely vegetated ecosystems",
    "Inland wetlands",
    "Rivers and canals",
    "Lakes and reservoirs",
    "Marine inlets and transitional waters",
    "Coastal beaches, dunes and wetlands",
    "Marine ecosystems",
]

# ---------------------------------------------------------------------------
# CORINE Land Cover (CLC) 3-digit code -> EU ecosystem type level 1.
# MAES-based crosswalk. VERIFY against the official EEA/MAES correspondence
# table before production use; coastal beaches (331 near coast) may need a
# spatial rule rather than a pure code mapping.
# ---------------------------------------------------------------------------
CLC_TO_ECOSYSTEM_L1 = {
    # Settlements and other artificial areas
    111: 0, 112: 0, 121: 0, 122: 0, 123: 0, 124: 0,
    131: 0, 132: 0, 133: 0, 141: 0, 142: 0,
    # Cropland
    211: 1, 212: 1, 213: 1, 221: 1, 222: 1, 223: 1,
    241: 1, 242: 1, 243: 1, 244: 1,
    # Grassland
    231: 2, 321: 2,
    # Forest and woodland
    311: 3, 312: 3, 313: 3,
    # Heathland and shrub
    322: 4, 323: 4, 324: 4,
    # Sparsely vegetated ecosystems
    332: 5, 333: 5, 334: 5, 335: 5,
    # Inland wetlands
    411: 6, 412: 6,
    # Rivers and canals
    511: 7,
    # Lakes and reservoirs
    512: 8,
    # Marine inlets and transitional waters
    421: 9, 423: 9, 521: 9, 522: 9,
    # Coastal beaches, dunes and wetlands
    331: 10, 422: 10,
    # Marine ecosystems
    523: 11,
}

# ---------------------------------------------------------------------------
# Annex 2 (guidance note): default annual-average Vd by ecosystem type
# (basic-approach fallback), cm/s. Ireland/UK-derived; replace with national
# values where available. Values below are PLACEHOLDERS ordered like
# ECOSYSTEM_TYPES_L1 - fill from the guidance note Annex 2 table before use.
# ---------------------------------------------------------------------------
ANNEX2_DEFAULT_VD_CMS = {
    "PM2.5": {
        "Settlements and other artificial areas": None,
        "Cropland": None,
        "Grassland": None,
        "Forest and woodland": None,
        "Heathland and shrub": None,
        "Sparsely vegetated ecosystems": None,
        "Inland wetlands": None,
        "Rivers and canals": None,
        "Lakes and reservoirs": None,
        "Marine inlets and transitional waters": None,
        "Coastal beaches, dunes and wetlands": None,
        "Marine ecosystems": None,
    }
}

DEFAULT_CRS = "EPSG:3301"  # L-EST97 (Estonian national grid)


# ---------------------------------------------------------------------------
# Phenology (offline mode): monthly LAI as a FRACTION of the summer peak, for
# hemiboreal (Estonia) vegetation classes. Jan..Dec. Used to turn a single
# summer LAI raster into a seasonal LAI stack when CLMS multi-temporal LAI is
# not downloaded. These are typical values - refine with real monthly LAI.
# ---------------------------------------------------------------------------
PHENOLOGY_PROFILES = {
    "deciduous": [0.05, 0.05, 0.05, 0.15, 0.55, 0.90, 1.00, 0.95, 0.70, 0.30, 0.10, 0.05],
    "evergreen": [0.80, 0.80, 0.82, 0.85, 0.92, 0.98, 1.00, 1.00, 0.97, 0.92, 0.85, 0.80],
    "crop":      [0.05, 0.05, 0.08, 0.20, 0.55, 0.85, 1.00, 0.80, 0.45, 0.20, 0.08, 0.05],
    "grass":     [0.10, 0.10, 0.15, 0.35, 0.70, 0.95, 1.00, 0.92, 0.75, 0.45, 0.20, 0.12],
}

# ecosystem-type index (see ECOSYSTEM_TYPES_L1) -> phenology blend weights
ECOSYSTEM_PHENOLOGY_BLEND = {
    0:  {"deciduous": 0.70, "evergreen": 0.20, "grass": 0.10},  # Settlements
    1:  {"crop": 0.90, "grass": 0.10},                          # Cropland
    2:  {"grass": 1.00},                                        # Grassland
    3:  {"evergreen": 0.51, "deciduous": 0.49},                 # Forest and woodland
    4:  {"evergreen": 0.40, "deciduous": 0.40, "grass": 0.20},  # Heathland and shrub
    5:  {"grass": 0.70, "deciduous": 0.30},                     # Sparsely vegetated
    6:  {"grass": 0.75, "deciduous": 0.25},                     # Inland wetlands
    7:  {"grass": 0.60, "deciduous": 0.40},                     # Rivers and canals
    8:  {"grass": 0.60, "deciduous": 0.40},                     # Lakes and reservoirs
    9:  {"grass": 0.60, "deciduous": 0.40},                     # Marine inlets
    10: {"grass": 0.70, "deciduous": 0.30},                     # Coastal beaches
    11: {"grass": 0.60, "deciduous": 0.40},                     # Marine
}

DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


# ---------------------------------------------------------------------------
# Statistics Estonia ecosystem extent map, ecosystem type LEVEL 2 (30 classes,
# raster value = code 1..30; stat_EU_II.tif, version 08.09.2026).
# (code, name, level-1 index into ECOSYSTEM_TYPES_L1, phenology blend)
# Used by the daily production pipeline (run_daily) - 2024 report.
# ---------------------------------------------------------------------------
_SETTL = {"deciduous": 0.70, "evergreen": 0.20, "grass": 0.10}
_WET = {"grass": 0.75, "deciduous": 0.25}
_AQ = {"grass": 0.60, "deciduous": 0.40}
_SPARSE = {"grass": 0.70, "deciduous": 0.30}
STAT_L2_CLASSES = [
    (1, "Annual cropland", 1, {"crop": 0.90, "grass": 0.10}),
    (2, "Sown pastures and fields (modified grasslands)", 2, {"grass": 1.00}),
    (3, "Permanent crops", 1, {"deciduous": 1.00}),
    (4, "Broadleaved deciduous forest", 3, {"deciduous": 1.00}),
    (5, "Coniferous forests", 3, {"evergreen": 1.00}),
    (6, "Mixed forests", 3, {"evergreen": 0.50, "deciduous": 0.50}),
    (7, "Mires, bogs and fens", 6, _WET),
    (8, "Natural and semi-natural grassland", 2, {"grass": 1.00}),
    (9, "Inland marshes and other wetlands on mineral soil", 6, _WET),
    (10, "Heathland and (sub-) alpine shrub", 4, {"evergreen": 0.40, "deciduous": 0.40, "grass": 0.20}),
    (11, "Other artificial areas", 0, _SETTL),
    (12, "Semi-desert, desert and other sparsely vegetated areas", 5, _SPARSE),
    (13, "Infrastructure and industrial areas", 0, _SETTL),
    (14, "Urban greenspace", 0, _SETTL),
    (15, "Coastal dunes, beaches and sandy and muddy shores", 10, _SPARSE),
    (16, "Mixed farmland", 1, {"crop": 0.70, "grass": 0.30}),
    (17, "Lakes and ponds", 8, _AQ),
    (18, "Canals, ditches and drains", 7, _AQ),
    (19, "Artificial reservoirs", 8, _AQ),
    (20, "Rivers and streams", 7, _AQ),
    (21, "Continuous settlement area", 0, _SETTL),
    (22, "Discontinuous settlement area", 0, _SETTL),
    (23, "Bare rocks", 5, _SPARSE),
    (24, "Coastal lagoons", 9, _AQ),
    (25, "Estuaries and bays", 9, _AQ),
    (26, "Rocky shores", 10, _SPARSE),
    (27, "Marine macrophyte habitats", 11, _AQ),
    (28, "Subtidal sand beds and mud plains", 11, _AQ),
    (29, "Shellfish beds and reefs", 11, _AQ),
    (30, "Subtidal rocky substrates", 11, _AQ),
]

# Evergreen share of a 1 km cell used for the winter-LAI correction of the
# Sentinel-3 LAI: sum over level-2 classes of (area share x weight).
STAT_EVERGREEN_WEIGHTS = {5: 1.0, 6: 0.5, 10: 0.4}

SECONDS_PER_DAY = 86400.0
