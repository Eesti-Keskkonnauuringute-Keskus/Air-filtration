from pathlib import Path

from air_filtration.acquire_wind import _read_rc
from air_filtration.config import Config

ROOT = Path(__file__).resolve().parents[1]


def test_read_rc_parses_url_and_key(tmp_path):
    rc = tmp_path / ".cdsapirc"
    rc.write_text("# comment\nurl: https://cds.climate.copernicus.eu/api/\nkey: abc-123\n", encoding="utf-8")
    assert _read_rc(rc) == {"url": "https://cds.climate.copernicus.eu/api", "key": "abc-123"}


def test_tilde_paths_expand_to_home():
    cfg = Config(cds_rc_path="~/.cdsapirc_cds", cache_dir="~/af_cache", output_dir="out")
    assert cfg.cds_rc_path == str(Path("~/.cdsapirc_cds").expanduser())
    assert cfg.cache_dir == str(Path("~/af_cache").expanduser())
    assert cfg.output_dir == "out"


def test_production_config_is_portable():
    """No machine-specific absolute paths; inputs shipped in the repo exist."""
    text = (ROOT / "config_daily_2024.yaml").read_text(encoding="utf-8")
    assert ":/" not in text.replace("https://", "")
    cfg = Config.from_yaml(ROOT / "config_daily_2024.yaml")
    assert (ROOT / cfg.lai_peak_path).exists()
    assert (ROOT / cfg.boundary_path).exists()
