"""Interaktiivne töövoog: kõik sammud ühe käivitusega, iga sammu juures küsitakse,
kas jooksutada uuesti või jätta olemasolevad tulemused alles.

    python run_air_filtration.py                                   (küsib seadistusfaili)
    python run_air_filtration.py --config config_daily_2024.yaml
    python run_air_filtration.py --config config_daily_2024.yaml --auto    (küsimusteta, vaikevalikud)

Sammud (vt docs/toovoog.png):
  0  seadistus + sisendfailide kontroll (+ soovi korral testid)
  1  tuul      ERA5-Land tunnine u/v      -> <cache_dir>/era5land_hourly_wind_YYYY_MM.nc
  2  LAI       Sentinel-3 dekaadid        -> <lai_dir>/*.nc
  3  eeltöötlus (vahemälu)               -> <cache_dir>/daily_YYYY/*.npy
  4  arvutus + tabelid, GeoTIFF, shp      -> <output_dir>/
  5  kaardid                              -> <output_dir>/figures/

Midagi ei kustutata: "uuesti" puhul tõstetakse vanad failid kausta
<cache_dir>/_vana/<aeg>/ või _arhiiv/<output_dir>_<aeg>/.
Kui samm tehakse uuesti, märgitakse sellest sõltuvad järgmised sammud vananenuks.
"""
from __future__ import annotations

import argparse
import dataclasses
import glob
import logging
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from .config import Config

log = logging.getLogger(__name__)

LAI_AREA = [59.9, 21.4, 57.3, 28.3]          # N, W, S, E (Eesti + puhver)
LAI_EXPECTED = 36                              # dekaadi aastas
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

# vahemälufail -> mis sisendist see tehakse (sammu nimi)
CACHE_FILES = {
    "conc_daily.npy": "Airviro kontsentratsioon",
    "vdlai_daily.npy": "tuul (Vd(LAI))",
    "wind_daily.npy": "tuul (tuulekiirus)",
    "lai_satellite_daily.npy": "LAI",
    "ecosystem_area_m2.npy": "ökosüsteemide kaart",
}


# --------------------------------------------------------------------------- #
# abifunktsioonid
# --------------------------------------------------------------------------- #
class Katkesta(Exception):
    pass


class Kysija:
    """Küsib kasutajalt valiku; --auto korral tagastab vaikevaliku."""

    def __init__(self, auto: bool = False, inp=None):
        self.auto, self.inp = auto, (inp or (lambda prompt: input(prompt)))

    def __call__(self, kysimus: str, valikud: dict, vaikimisi: str) -> str:
        rida = " / ".join(f"[{k.upper() if k == vaikimisi else k}] {v}" for k, v in valikud.items())
        if self.auto:
            print(f"  {kysimus}\n    {rida}  ->  {vaikimisi} (auto)")
            return vaikimisi
        while True:
            vastus = self.inp(f"  {kysimus}\n    {rida} / [q] katkesta\n    valik (Enter = {vaikimisi}): ").strip().lower()
            if vastus == "":
                return vaikimisi
            if vastus in ("q", "quit", "katkesta"):
                raise Katkesta()
            if vastus in valikud:
                return vastus
            print("    ? tundmatu valik")


def pealkiri(n, tekst):
    print(f"\n{'=' * 72}\n {n}. {tekst}\n{'=' * 72}")


def aeg(p: Path) -> str:
    return datetime.fromtimestamp(p.stat().st_mtime).strftime("%d.%m.%Y %H:%M")


def mtime(paths) -> float:
    m = [Path(p).stat().st_mtime for p in paths if Path(p).exists()]
    return max(m) if m else 0.0


def arhiveeri(paths, siht: Path) -> Path:
    """Tõstab failid/kaustad kausta `siht` (midagi ei kustutata)."""
    siht.mkdir(parents=True, exist_ok=True)
    for p in paths:
        p = Path(p)
        if p.exists():
            shutil.move(str(p), str(siht / p.name))
    print(f"    vanad failid tõstetud: {siht}")
    return siht


def wind_paths(cfg: Config) -> list[Path]:
    from .acquire_wind import hourly_wind_paths
    return hourly_wind_paths(cfg)


def lai_files(cfg: Config) -> list[Path]:
    return sorted(Path(p) for p in glob.glob(str(Path(cfg.lai_dir) / "*.nc")))


def cache_dir(cfg: Config) -> Path:
    return Path(cfg.cache_dir) / f"daily_{cfg.reference_year}"


def cache_status(cfg: Config) -> dict:
    """{fail: (olemas, vananenud, põhjus)} - vananenud = allikas on uuem kui vahemälu."""
    cd = cache_dir(cfg)
    allikas = {
        "conc_daily.npy": [cfg.conc_daily_path],
        "vdlai_daily.npy": wind_paths(cfg),
        "wind_daily.npy": wind_paths(cfg),
        "lai_satellite_daily.npy": lai_files(cfg),
        "ecosystem_area_m2.npy": [cfg.ecosystem_extent_path],
    }
    out = {}
    for f, src in allikas.items():
        p = cd / f
        if not p.exists():
            out[f] = (False, True, "puudub")
        elif mtime(src) > p.stat().st_mtime:
            out[f] = (True, True, "sisend on uuem")
        else:
            out[f] = (True, False, f"ok ({aeg(p)})")
    return out


# --------------------------------------------------------------------------- #
# sammud
# --------------------------------------------------------------------------- #
def vali_config(arg: str | None, kysi: Kysija) -> Path:
    if arg:
        return Path(arg)
    kandidaadid = sorted(Path(".").glob("config_daily_*.yaml"))
    if not kandidaadid:
        raise SystemExit("Tööriista kaustas pole ühtegi config_daily_*.yaml faili (kas oled õiges kaustas?).")
    if len(kandidaadid) == 1 or kysi.auto:
        return kandidaadid[-1]
    valikud = {str(i + 1): p.name for i, p in enumerate(kandidaadid)}
    return kandidaadid[int(kysi("Milline seadistusfail?", valikud, str(len(kandidaadid)))) - 1]


def samm0(cfg: Config, cfg_path: Path, kysi: Kysija):
    pealkiri(0, f"Seadistus ja sisendid  ({cfg_path.name}, aasta {cfg.reference_year})")
    kontroll = [("Airviro ööpäevakeskmised (conc_daily_path)", cfg.conc_daily_path, True),
                ("STAT ökosüsteemide kaart (ecosystem_extent_path)", cfg.ecosystem_extent_path, True),
                ("Maakonnapiirid (boundary_path)", cfg.boundary_path, True),
                ("PROBA-V LAI tipp (lai_peak_path)", cfg.lai_peak_path, cfg.lai_mode == "hybrid"),
                ("CDS võti (cds_rc_path)", cfg.cds_rc_path or str(Path("~/.cdsapirc").expanduser()), False)]
    puudu = []
    for nimi, p, kohustuslik in kontroll:
        ok = bool(p) and Path(p).exists()
        print(f"  {'OK ' if ok else '-- '} {nimi}: {p}")
        if not ok and kohustuslik:
            puudu.append(nimi)
    print(f"  väljundkaust: {cfg.output_dir}   vahemälu: {cache_dir(cfg)}")
    if puudu:
        raise SystemExit("\nPuuduvad kohustuslikud sisendid: " + "; ".join(puudu) + "\nParanda seadistusfail.")
    if kysi("Kas käivitada testid (pytest)?", {"j": "jah", "e": "ei"}, "e") == "j":
        r = subprocess.run([sys.executable, "-m", "pytest", "-q"])
        if r.returncode != 0 and kysi("Testid ebaõnnestusid. Kas jätkata?", {"j": "jah", "e": "ei"}, "e") == "e":
            raise Katkesta()


def samm1_tuul(cfg: Config, kysi: Kysija) -> bool:
    """Tagastab True, kui tuulefailid muutusid."""
    pealkiri(1, "Tuul: ERA5-Land tunnine 10 m u/v (CDS)")
    paths = wind_paths(cfg)
    olemas = [p for p in paths if p.exists()]
    print(f"  kuufaile olemas: {len(olemas)}/12  ({paths[0].parent})")
    if len(olemas) == 12:
        print(f"  viimati muudetud: {aeg(max(olemas, key=lambda p: p.stat().st_mtime))}")
        v = kysi("Tuuleandmed on olemas.", {"k": "kasuta olemasolevaid", "u": "laadi kõik uuesti"}, "k")
    elif olemas:
        v = kysi("Osa kuid puudub.", {"p": "laadi puuduvad kuud", "u": "laadi kõik uuesti", "k": "jäta nii"}, "p")
    else:
        v = kysi("Tuuleandmed puuduvad (allalaadimine ~30–60 min).", {"p": "laadi alla", "k": "jäta vahele"}, "p")
    if v == "k":
        return False
    if v == "u":
        vanad = olemas + [p.with_suffix(".unzipped") for p in paths if p.with_suffix(".unzipped").exists()]
        arhiveeri(vanad, Path(cfg.cache_dir) / "_vana" / f"tuul_{STAMP}")
    from .acquire_wind import download_era5_hourly_wind_year
    download_era5_hourly_wind_year(cfg)
    if kysi("Kas teha tuule kontrolltabel (tunnine vs päeva- vs kuukeskmine tuul)?",
            {"j": "jah", "e": "ei"}, "e") == "j":
        _tuule_kontroll(cfg, paths)
    return True


def _tuule_kontroll(cfg, paths):
    import csv
    from .acquire_wind import monthly_vdlai_from_hourly
    _, _, _, rows = monthly_vdlai_from_hourly(paths)
    out = Path(cfg.output_dir); out.mkdir(parents=True, exist_ok=True)
    fn = out / f"tuul_Vd_kontroll_{cfg.reference_year}.csv"
    with open(fn, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    print(f"    kontrolltabel: {fn}")


def samm2_lai(cfg: Config, kysi: Kysija) -> bool:
    pealkiri(2, "LAI: Sentinel-3 dekaadid (CDS)")
    files = lai_files(cfg)
    print(f"  dekaadifaile: {len(files)} (oodatav ~{LAI_EXPECTED})  ({cfg.lai_dir})")
    if len(files) >= LAI_EXPECTED:
        v = kysi("LAI andmed on olemas.", {"k": "kasuta olemasolevaid", "u": "laadi uuesti"}, "k")
    elif files:
        v = kysi("LAI faile on vähem kui oodatud.", {"u": "laadi kõik uuesti", "k": "kasuta olemasolevaid"}, "u")
    else:
        v = kysi("LAI andmed puuduvad.", {"u": "laadi alla", "k": "jäta vahele"}, "u")
    if v == "k":
        return False
    lai_dir = Path(cfg.lai_dir)
    if files:   # download_lai_dekads kasutab olemasolevaid, seega tõsta vanad eest ära
        arhiveeri(list(lai_dir.iterdir()), Path(cfg.cache_dir) / "_vana" / f"lai_{STAMP}")
    from .acquire_lai import download_lai_dekads
    got = download_lai_dekads(cfg.reference_year, lai_dir, cds_rc_path=cfg.cds_rc_path, area=LAI_AREA)
    print(f"    alla laaditud {len(got)} dekaadifaili")
    return True


def samm3_eeltootlus(cfg: Config, kysi: Kysija, muutus: dict) -> bool:
    pealkiri(3, f"Eeltöötlus: vahemälu {cache_dir(cfg)}")
    st = cache_status(cfg)
    # kui sel käivitusel laaditi tuul/LAI uuesti, on vastav vahemälu kindlasti vana
    for f in st:
        if (muutus.get("tuul") and f in ("vdlai_daily.npy", "wind_daily.npy")) or \
           (muutus.get("lai") and f == "lai_satellite_daily.npy"):
            st[f] = (st[f][0], True, "sisend laaditi uuesti")
    for f, (olemas, vana, pohjus) in st.items():
        print(f"  {'!! ' if vana else 'OK '} {f:26s} {CACHE_FILES[f]:28s} {pohjus}")
    vanad = [f for f, s in st.items() if s[1]]
    if vanad:
        v = kysi(f"{len(vanad)} vahemälufaili tuleb (uuesti) arvutada.",
                 {"v": "arvuta vananenud", "u": "arvuta kõik uuesti", "k": "jäta nii (EI soovita)"}, "v")
    else:
        v = kysi("Vahemälu on ajakohane.", {"k": "kasuta olemasolevat", "u": "arvuta kõik uuesti",
                                             "x": "vali failid ise"}, "k")
    if v == "k":
        return False
    if v == "x":
        vanad = [f for f in st if kysi(f"Arvutada {f} uuesti?", {"j": "jah", "e": "ei"}, "e") == "j"]
    elif v == "u":
        vanad = list(st)
    cd = cache_dir(cfg)
    if "vdlai_daily.npy" in vanad or "wind_daily.npy" in vanad:     # tehakse koos
        vanad = sorted(set(vanad) | {"vdlai_daily.npy", "wind_daily.npy"})
    olemas = [cd / f for f in vanad if (cd / f).exists()]
    if olemas:
        arhiveeri(olemas, Path(cfg.cache_dir) / "_vana" / f"daily_{cfg.reference_year}_{STAMP}")
    if not vanad:
        return False
    t = time.time()
    from .run_daily import prepare_inputs
    prepare_inputs(cfg)
    print(f"    eeltöötlus valmis ({time.time() - t:.0f} s)")
    return True


def _kokkuvote(xlsx: Path):
    try:
        import pandas as pd
        s = pd.read_excel(xlsx, "summary")
        for r in s.itertuples():
            p = r.pct_of_national_PM25_emissions
            pct = f"  ({p:.1f}% heitest)" if pd.notna(p) else ""
            print(f"    {r.run:22s} {r.total_t_per_yr:9.2f} t/a{pct}")
    except Exception as e:      # noqa: BLE001
        print(f"    (kokkuvõtet ei saanud lugeda: {e})")


def samm4_arvutus(cfg: Config, kysi: Kysija, muutus: dict) -> bool:
    pealkiri(4, f"Arvutus ja väljundid -> {cfg.output_dir}")
    out = Path(cfg.output_dir)
    xlsx = out / f"air_filtration_daily_{cfg.reference_year}.xlsx"
    if xlsx.exists():
        print(f"  olemasolevad tulemused ({aeg(xlsx)}):")
        _kokkuvote(xlsx)
        uuem_sisend = mtime(cache_dir(cfg).glob("*.npy")) > xlsx.stat().st_mtime
        vaikimisi = "j" if (any(muutus.values()) or uuem_sisend) else "e"
        if vaikimisi == "j":
            print("  NB! sisendid on pärast viimast arvutust muutunud.")
        v = kysi("Kas arvutada uuesti?", {"j": "jah, kirjuta üle", "a": "jah, vanad tulemused arhiivi",
                                          "e": "ei, jäta olemasolevad"}, vaikimisi)
    else:
        v = kysi("Tulemusi veel pole.", {"j": "arvuta", "e": "jäta vahele"}, "j")
    if v == "e":
        return False
    if v == "a":
        arhiveeri([out], Path("_arhiiv") / f"{out.name}_{STAMP}")
    joonised = kysi("Kas teha samas ka kaardid (fig1–fig6)?", {"j": "jah", "e": "ei"},
                    "j" if cfg.make_figures else "e") == "j"
    t = time.time()
    from .run_daily import run_daily
    res = run_daily(cfg=dataclasses.replace(cfg, make_figures=joonised))
    print(f"\n  arvutus valmis ({time.time() - t:.0f} s):")
    _kokkuvote(xlsx)
    muutus["joonised_tehtud"] = joonised
    return True


def samm5_kaardid(cfg: Config, kysi: Kysija, muutus: dict):
    pealkiri(5, f"Kaardid -> {Path(cfg.output_dir) / 'figures'}")
    if muutus.get("joonised_tehtud"):
        print("  tehti sammus 4 – vahele jäetud.")
        return
    fig = Path(cfg.output_dir) / "figures"
    olemas = sorted(fig.glob("fig*.png")) + sorted(fig.glob("fig*.jpg"))
    print(f"  kaarte olemas: {len(olemas)}" + (f" ({aeg(olemas[0])})" if olemas else ""))
    if kysi("Kas joonistada kaardid uuesti?", {"j": "jah", "e": "ei"}, "e" if olemas else "j") == "e":
        return
    from .run_daily import prepare_inputs, deposition
    from .figures import report_figures
    inp = prepare_inputs(cfg)
    dep, _ = deposition(inp, cfg, cfg.lai_mode)
    report_figures(cfg, inp, dep, fig)
    print(f"    kaardid: {fig}")


# --------------------------------------------------------------------------- #
def main(argv=None):
    ap = argparse.ArgumentParser(prog="run_air_filtration", description="Õhufiltratsiooni töövoog sammhaaval.")
    ap.add_argument("--config", help="seadistusfail (vaikimisi küsitakse)")
    ap.add_argument("--auto", action="store_true", help="küsimusteta: olemasolev kasutatakse, puuduv tehakse")
    ap.add_argument("--alates", type=int, default=0, choices=range(0, 6), help="alusta sammust N (0–5)")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="    %(asctime)s %(message)s", datefmt="%H:%M:%S")
    kysi = Kysija(auto=a.auto)
    muutus = {}
    try:
        cfg_path = vali_config(a.config, kysi)
        cfg = Config.from_yaml(cfg_path)
        print(f"\nÕhufiltratsiooni töövoog – {cfg_path.name}, aasta {cfg.reference_year}"
              f"{'  [auto]' if a.auto else ''}\nEnter = suurtähega vaikevalik, q = katkesta.")
        if a.alates <= 0: samm0(cfg, cfg_path, kysi)
        if a.alates <= 1: muutus["tuul"] = samm1_tuul(cfg, kysi)
        if a.alates <= 2: muutus["lai"] = samm2_lai(cfg, kysi)
        if a.alates <= 3: muutus["vahemalu"] = samm3_eeltootlus(cfg, kysi, muutus)
        if a.alates <= 4: samm4_arvutus(cfg, kysi, muutus)
        samm5_kaardid(cfg, kysi, muutus)
    except (Katkesta, KeyboardInterrupt):
        print("\nKatkestatud. Juba tehtud sammude tulemused on alles.")
        return 1
    print(f"\nValmis. Tulemused: {Path(cfg.output_dir).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
