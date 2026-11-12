import numpy as np
from air_filtration.vd import (vdlai_from_wind, vdlai_time_integrated,
                               vd_from_lai_wind, wind_integration_diagnostic)


def test_table_a1_exact_points():
    # tabulated values reproduced exactly at integer wind speeds
    assert vdlai_from_wind(0) == 0.0
    assert abs(vdlai_from_wind(2) - 0.087) < 1e-12
    assert abs(vdlai_from_wind(7) - 0.504) < 1e-12
    assert abs(vdlai_from_wind(10) - 1.836) < 1e-12


def test_interpolation_and_clamp():
    # midpoint between 2 (0.087) and 3 (0.143)
    assert abs(vdlai_from_wind(2.5) - (0.087 + 0.143) / 2) < 1e-12
    # clamp beyond the table
    assert vdlai_from_wind(-5) == 0.0
    assert vdlai_from_wind(99) == vdlai_from_wind(13)


def test_vd_equation():
    # Vd = Vd(LAI) * LAI ; at 4 m/s Vd(LAI)=0.160, LAI=5 -> 0.80 cm/s
    assert abs(vd_from_lai_wind(5.0, 4.0) - 0.160 * 5.0) < 1e-9


def test_time_integration_beats_mean_in_convex_regime():
    # a wind series spanning calm + storm: integrating Vd(LAI) must exceed
    # Vd(LAI) at the mean wind, because the function is convex at high wind.
    wind = np.array([2.0, 2.0, 10.0, 10.0])   # mean = 6 -> Vd(LAI)(6)=0.182
    integ = vdlai_time_integrated(wind)
    at_mean = vdlai_from_wind(wind.mean())
    assert integ > at_mean
    diag = wind_integration_diagnostic(wind)
    assert diag > 1.0


def test_time_integration_below_one_in_concave_regime():
    # low, variable wind (all < 6 m/s, concave region) -> variability lowers Vd
    wind = np.array([1.0, 2.0, 3.0, 4.0])
    assert wind_integration_diagnostic(wind) < 1.0
