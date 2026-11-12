"""
Deposition velocity (Vd) for PM2.5 - guidance note advanced approach.

    Vd = Vd(LAI) * LAI                                  (Eq. 2)

where Vd(LAI) is a non-linear function of wind speed (Table A1). The wind
dependence must be integrated over the wind time series, NOT evaluated at the
mean wind, because Vd(LAI) is strongly convex above ~7 m/s.
"""
from __future__ import annotations

import numpy as np

from .constants import TABLE_A1_WIND_MS, TABLE_A1_VDLAI_CMS


def vdlai_from_wind(wind_ms: np.ndarray) -> np.ndarray:
    """Vd(LAI) [cm/s] as a function of wind speed [m/s] via Table A1.

    Linear interpolation between tabulated points; values are clamped to the
    endpoints (0 and 13 m/s). Works on scalars or arrays of any shape.
    """
    w = np.asarray(wind_ms, dtype=float)
    w = np.clip(w, TABLE_A1_WIND_MS[0], TABLE_A1_WIND_MS[-1])
    return np.interp(w, TABLE_A1_WIND_MS, TABLE_A1_VDLAI_CMS)


def vdlai_time_integrated(wind_ms_timeseries: np.ndarray, axis: int = 0) -> np.ndarray:
    """Time-averaged Vd(LAI) [cm/s] over a wind time series.

    This is the *correct* way to reduce a wind time series to a single
    Vd(LAI): apply Table A1 per time step, then average - preserving the
    convex tail. Averaging the wind first and then applying Table A1 would
    under-represent windy periods.

    Parameters
    ----------
    wind_ms_timeseries : array, wind speed [m/s] with a time axis.
    axis : the time axis to reduce over.
    """
    vd = vdlai_from_wind(wind_ms_timeseries)
    return np.nanmean(vd, axis=axis)


def vd_from_lai_wind(lai: np.ndarray, wind_ms: np.ndarray) -> np.ndarray:
    """Instantaneous/periodic Vd [cm/s] = Vd(LAI)(wind) * LAI (Eq. 2)."""
    return vdlai_from_wind(wind_ms) * np.asarray(lai, dtype=float)


def wind_integration_diagnostic(wind_ms_timeseries: np.ndarray, axis: int = 0) -> np.ndarray:
    """Diagnostic: <Vd(LAI)(w)> / Vd(LAI)(<w>).

    >1 means the time-varying wind raises Vd relative to the mean-wind
    approximation (convex regime, windy/coastal); <1 in the concave low-wind
    regime. Quantifies the error of using mean wind.
    """
    mean_wind = np.nanmean(wind_ms_timeseries, axis=axis)
    integ = vdlai_time_integrated(wind_ms_timeseries, axis=axis)
    at_mean = vdlai_from_wind(mean_wind)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(at_mean > 0, integ / at_mean, np.nan)
