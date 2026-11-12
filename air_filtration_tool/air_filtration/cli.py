"""Command-line interface.

    python -m air_filtration daily    --config config_daily_2024.yaml   # full calculation
    python -m air_filtration figures  --config config_daily_2024.yaml   # maps only
    python -m air_filtration workflow --config config_daily_2024.yaml   # interactive, step by step
    python -m air_filtration peak-lai --source <PROBA-V LAI .nc> [--source ...] --out data/LAI_peak.tif
"""
from __future__ import annotations

import argparse
import json
import logging
import sys


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    if argv and argv[0] == "workflow":          # interaktiivne töövoog (oma argumendid)
        from .workflow import main as wf
        return wf(argv[1:])

    p = argparse.ArgumentParser(prog="air_filtration",
                                description="PM2.5 air-filtration ecosystem-service model (Eurostat guidance note).")
    sub = p.add_subparsers(dest="command", required=True)
    for cmd, hlp in (("daily", "full calculation: tables, rasters, shapefile, maps"),
                     ("figures", "redraw the report maps only")):
        sp = sub.add_parser(cmd, help=hlp)
        sp.add_argument("--config", required=True, help="Path to config YAML")
        sp.add_argument("--verbose", "-v", action="store_true")
    sp = sub.add_parser("peak-lai", help="build the PROBA-V summer peak LAI raster from CLMS LAI 1 km V2 NetCDF")
    sp.add_argument("--source", required=True, action="append",
                    help="c_gls_LAI-RT6_<date>_GLOBE_PROBAV_V2.0.1.nc (repeat for several dekads -> maximum)")
    sp.add_argument("--out", required=True, help="output GeoTIFF")
    sp.add_argument("--verbose", "-v", action="store_true")
    sub.add_parser("workflow", help="interactive step-by-step run (see run_air_filtration.py)")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if args.command == "daily":
        from .run_daily import run_daily
        result = run_daily(args.config)
        print(json.dumps(result, indent=2, default=str))
    elif args.command == "figures":
        from pathlib import Path
        from .config import Config
        from .run_daily import prepare_inputs, deposition
        from .figures import report_figures
        cfg = Config.from_yaml(args.config)
        inp = prepare_inputs(cfg)
        dep, _ = deposition(inp, cfg, cfg.lai_mode)
        print(json.dumps(report_figures(cfg, inp, dep, Path(cfg.output_dir) / "figures"), indent=2, default=str))
    elif args.command == "peak-lai":
        from .acquire_lai import peak_lai_from_clms
        print(peak_lai_from_clms(args.source, args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
