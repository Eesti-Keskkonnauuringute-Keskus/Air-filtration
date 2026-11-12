"""Unit tests for the daily production pipeline building blocks (no I/O)."""
import numpy as np

from air_filtration import daily_inputs as di
from air_filtration.constants import (STAT_L2_CLASSES, ECOSYSTEM_TYPES_L1, UNIT_FACTOR_PER_SECOND,
                                      SECONDS_PER_DAY, PHENOLOGY_PROFILES)


def test_stat_crosswalk_complete():
    assert [c[0] for c in STAT_L2_CLASSES] == list(range(1, 31))
    assert all(0 <= c[2] < len(ECOSYSTEM_TYPES_L1) for c in STAT_L2_CLASSES)
    for _, _, _, blend in STAT_L2_CLASSES:
        assert abs(sum(blend.values()) - 1) < 1e-9
        assert set(blend) <= set(PHENOLOGY_PROFILES)


def test_daily_factor_equals_guidance_formula():
    # 8.64e-6 per day == 3.1536e-3 / 365
    f = UNIT_FACTOR_PER_SECOND["t_per_ha_per_yr"] * SECONDS_PER_DAY
    assert abs(f - 3.1536e-3 / 365) < 1e-15
    # constant Vd, C over 365 days reproduces the annual guidance formula
    vd, c = 0.3, 3.0
    assert abs(365 * vd * c * f - vd * c * 3.1536e-3) < 1e-12


def test_evergreen_correction_keeps_winter_lai():
    days = di.year_days(2024)
    t = np.arange(len(days))
    ls = np.clip(np.sin((t - 80) / 366 * 2 * np.pi), 0, None)[:, None, None] * 3.0   # winter 0, peak 3
    fe = np.array([[0.0, 1.0]])
    LS = np.repeat(ls, 2, axis=2)
    out = di.evergreen_correction(LS, fe, days)
    assert np.allclose(out[:, 0, 0], LS[:, 0, 0])            # no evergreen -> unchanged
    assert out[0, 0, 1] >= 0.8 * LS[:, 0, 1].max() - 1e-4      # January evergreen >= 80 % of peak
    assert np.isclose(out[:, 0, 1].max(), LS[:, 0, 1].max())  # peak unchanged


def test_hybrid_rescales_to_peak():
    LS = np.array([0.5, 1.0, 2.0, 1.0])[:, None, None] * np.ones((1, 1, 2))
    peak = np.array([[4.0, 6.0]])
    H = di.hybrid_lai(LS.astype(np.float32), peak)
    assert np.allclose(H[:, 0, 0], [1.0, 2.0, 4.0, 2.0])
    assert np.allclose(H[:, 0, 1].max(), 6.0)


def test_class_phenology_shape():
    p = di.class_phenology_daily(di.year_days(2024))
    assert p.shape == (30, 366) and np.all(p > 0) and np.all(p <= 1.0001)
