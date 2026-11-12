"""Tests for the interactive workflow runner (no downloads, no heavy I/O)."""
import os
import time
from pathlib import Path

import numpy as np
import pytest

from air_filtration import workflow as wf
from air_filtration.config import Config


def _cfg(tmp_path):
    (tmp_path / "conc.nc").write_text("x"); (tmp_path / "eco.tif").write_text("x")
    lai = tmp_path / "lai"; lai.mkdir()
    return Config(reference_year=2024, cache_dir=str(tmp_path / "cache"), lai_dir=str(lai),
                  conc_daily_path=str(tmp_path / "conc.nc"), ecosystem_extent_path=str(tmp_path / "eco.tif"),
                  era5_wind_dataset="reanalysis-era5-land", output_dir=str(tmp_path / "out"))


def test_kysija_auto_and_input():
    assert wf.Kysija(auto=True)("?", {"k": "a", "u": "b"}, "k") == "k"
    answers = iter(["zz", "u"])
    assert wf.Kysija(inp=lambda _: next(answers))("?", {"k": "a", "u": "b"}, "k") == "u"
    assert wf.Kysija(inp=lambda _: "")("?", {"k": "a", "u": "b"}, "u") == "u"
    with pytest.raises(wf.Katkesta):
        wf.Kysija(inp=lambda _: "q")("?", {"k": "a"}, "k")


def test_wind_paths_names(tmp_path):
    p = wf.wind_paths(_cfg(tmp_path))
    assert len(p) == 12 and p[0].name == "era5land_hourly_wind_2024_01.nc"


def test_cache_status_missing_ok_stale(tmp_path):
    cfg = _cfg(tmp_path)
    st = wf.cache_status(cfg)
    assert all(not s[0] and s[1] for s in st.values())          # all missing
    cd = wf.cache_dir(cfg); cd.mkdir(parents=True)
    for f in wf.CACHE_FILES:
        np.save(cd / f, np.zeros(1))
    old = time.time() - 100
    os.utime(tmp_path / "conc.nc", (old, old)); os.utime(tmp_path / "eco.tif", (old, old))
    st = wf.cache_status(cfg)
    assert not any(s[1] for s in st.values())                    # all fresh
    os.utime(tmp_path / "conc.nc", None)                          # source touched now
    os.utime(cd / "conc_daily.npy", (old, old))
    assert wf.cache_status(cfg)["conc_daily.npy"][1]


def test_wind_step_keeps_complete_set(tmp_path):
    cfg = _cfg(tmp_path)
    for p in wf.wind_paths(cfg):
        p.parent.mkdir(parents=True, exist_ok=True); p.write_text("x")
    assert wf.samm1_tuul(cfg, wf.Kysija(auto=True)) is False


def test_prep_step_archives_and_rebuilds_stale(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    cd = wf.cache_dir(cfg); cd.mkdir(parents=True)
    for f in wf.CACHE_FILES:
        np.save(cd / f, np.zeros(1))
    called = []
    import air_filtration.run_daily as rd
    monkeypatch.setattr(rd, "prepare_inputs", lambda c: called.append(1))
    # LAI re-downloaded in this session -> its cache file must be rebuilt, others kept
    assert wf.samm3_eeltootlus(cfg, wf.Kysija(auto=True), {"lai": True}) is True
    assert called and not (cd / "lai_satellite_daily.npy").exists()
    assert (cd / "conc_daily.npy").exists()
    arch = list((Path(cfg.cache_dir) / "_vana").glob("daily_2024_*/lai_satellite_daily.npy"))
    assert len(arch) == 1
