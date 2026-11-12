"""Report maps (2024 report layout): white background, whole Estonia, legend east
of Lake Peipsi (outside the map), north arrow above and scale bar below the legend.

  fig1_conc.png  PM2.5 annual mean concentration
  fig2_wind.jpg  ERA5-Land annual mean wind speed
  fig3_lai.jpg   annual mean of the daily LAI used (main LAI mode)
  fig4_dep.png   PM2.5 deposition (main estimate)
  fig5_eco.png   Statistics Estonia ecosystem extent map (level 2)
  fig6_conc_10km.png  concentration as 10x10 km block means (if compare_10km)
Figure aspect ratios follow the content; ratios.json lists them (to size the
images in the Word report).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import warnings
# all-NaN cells (sea, outside Estonia) are expected; their numpy warnings are noise
warnings.filterwarnings("ignore", message="Mean of empty slice", category=RuntimeWarning)
warnings.filterwarnings("ignore", message="All-NaN slice encountered", category=RuntimeWarning)
import numpy as np

log = logging.getLogger(__name__)

STAT_COLOURS = ["#ffe680", "#ccf24d", "#e6a600", "#80ff00", "#00a600", "#4dff00", "#a6a6ff", "#e6e64d",
                "#4d4dff", "#a6ff80", "#cc4df2", "#cccccc", "#e6004d", "#ffa6ff", "#e6e6e6", "#f2cca6",
                "#80f2e6", "#00ccf2", "#4dccf2", "#00bfff", "#a60000", "#ff0000", "#999999", "#00ffa6",
                "#a6ffe6", "#b3b3b3", "#66cc99", "#99ccff", "#3366cc", "#6699cc"]
STAT_SHORT = ["Annual cropland", "Sown pastures and fields", "Permanent crops", "Broadleaved deciduous forest",
              "Coniferous forests", "Mixed forests", "Mires, bogs and fens", "Natural and semi-natural grassland",
              "Inland marshes and other wetlands", "Heathland and shrub", "Other artificial areas",
              "Sparsely vegetated areas", "Infrastructure and industrial areas", "Urban greenspace",
              "Coastal dunes, beaches and shores", "Mixed farmland", "Lakes and ponds", "Canals, ditches and drains",
              "Artificial reservoirs", "Rivers and streams", "Continuous settlement area",
              "Discontinuous settlement area", "Bare rocks", "Coastal lagoons", "Estuaries and bays", "Rocky shores",
              "Marine macrophyte habitats", "Subtidal sand beds and mud plains", "Shellfish beds and reefs",
              "Subtidal rocky substrates"]


def report_figures(cfg, inp: dict, dep_main: np.ndarray, out_dir, w_in: float = 11.0) -> dict:
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap, BoundaryNorm
    from matplotlib.patches import Patch
    import geopandas as gpd
    import rasterio
    from .run_daily import lai_for_mode

    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    grid, mask = inp["grid"], inp["mask"]
    H, W = grid.shape
    cty = gpd.read_file(cfg.boundary_path).to_crs(grid.crs)
    est = gpd.GeoSeries([cty.union_all() if hasattr(cty, "union_all") else cty.unary_union], crs=cty.crs)
    XB = cty.total_bounds
    ext = [grid.transform.c, grid.transform.c + W * grid.transform.a,
           grid.transform.f + H * grid.transform.e, grid.transform.f]
    ratios = {}

    def leg_bb(fig, ax, leg):
        fig.canvas.draw(); return leg.get_window_extent().transformed(ax.transData.inverted())

    def finalize(fig, ax, bounds, leg, name, pad=8000, arrow_h=42000, sb_h=16000):
        x0, y0, x1, y1 = bounds
        ax.set_xlim(x0 - pad, x1 + pad); ax.set_ylim(y0 - pad, y1 + pad)
        for _ in range(4):
            bb = leg_bb(fig, ax, leg)
            X0 = min(x0, bb.x0) - pad; X1 = max(x1, bb.x1) + pad
            Y0 = min(y0, bb.y0 - sb_h) - pad; Y1 = max(y1, bb.y1 + arrow_h) + pad
            r = (X1 - X0) / (Y1 - Y0)
            fig.set_size_inches(w_in, w_in / r); ax.set_xlim(X0, X1); ax.set_ylim(Y0, Y1)
            ax.set_aspect("equal", adjustable="box")
        bb = leg_bb(fig, ax, leg)
        xa = bb.x0 + 9000
        ax.annotate("N", xy=(xa, bb.y1 + arrow_h - 2000), xytext=(xa, bb.y1 + 6000), ha="center", va="bottom",
                    fontsize=12, fontweight="bold", zorder=5,
                    arrowprops=dict(arrowstyle="-|>,head_width=0.5,head_length=0.9", color="k", lw=2))
        xs = bb.x0 + 3000; ys = bb.y0 - sb_h + 3000
        for k in range(4):
            ax.add_patch(plt.Rectangle((xs + k * 12500, ys), 12500, 1800, fc="k" if k % 2 == 0 else "w",
                                       ec="k", lw=.6, zorder=5))
        for k, l in [(0, "0"), (2, "25"), (4, "50 km")]:
            ax.text(xs + k * 12500, ys + 3500, l, ha="center", fontsize=9, zorder=5)
        ratios[name] = r

    def base():
        fig = plt.figure(figsize=(w_in, w_in / 1.6)); ax = fig.add_axes([0, 0, 1, 1])
        ax.set_facecolor("white"); ax.set_xticks([]); ax.set_yticks([])
        for s in ax.spines.values(): s.set_edgecolor("0.6")
        return fig, ax

    def classed(arr, bins, colors, title, name, fmt="{:.2f}"):
        bins, colors = list(bins), list(colors)
        while len(bins) > 2 and bins[-1] <= bins[-2]:   # data max below a fixed break -> drop empty top class
            bins.pop(-2); colors.pop()
        fig, ax = base()
        ax.imshow(np.ma.masked_invalid(np.where(mask, arr, np.nan)), extent=ext, cmap=ListedColormap(colors),
                  norm=BoundaryNorm(bins, len(colors)), interpolation="nearest", zorder=1)
        cty.boundary.plot(ax=ax, color="0.45", lw=0.35, zorder=2)
        est.boundary.plot(ax=ax, color="0.25", lw=0.6, zorder=3)
        labs = [f"up to {fmt.format(bins[1])}" if i == 0 else f"{fmt.format(bins[i])} – {fmt.format(bins[i + 1])}"
                for i in range(len(colors))]
        leg = ax.legend([Patch(fc=c, ec="0.6", lw=.4) for c in colors], labs, title=title, loc="upper left",
                        bbox_to_anchor=(XB[2] + 6000, 6548000), bbox_transform=ax.transData, fontsize=10,
                        title_fontsize=10.5, frameon=False, alignment="left")
        finalize(fig, ax, XB, leg, name)
        fig.savefig(out / name, dpi=160, **({"pil_kwargs": {"quality": 92}} if name.endswith(".jpg") else {}))
        plt.close(fig)

    yr = cfg.reference_year
    Ca = np.nanmean(inp["C"], 0)
    # class breaks for the monitoring-corrected field (uniform background ~3.8 µg/m3, correction of 19.10.2026)
    c_bins = [0, 3.85, 3.9, 3.95, 4.0, 4.25, 4.5, 5.0, np.nanmax(Ca[mask]) + 0.01]
    c_cols = ["#f7fbf4", "#e3f1dc", "#c9e6c7", "#a6d6c3", "#7fc3c4", "#5aa6bf", "#3f7fae", "#2b5b8f"]
    classed(Ca, c_bins, c_cols, f"PM2.5 µg/m³ ({yr})", "fig1_conc.png")
    if getattr(cfg, "compare_10km", False):          # task 1.1.2: same field as 10x10 km block means
        from .io_raster import aggregate_1km_to_block
        C10 = aggregate_1km_to_block(Ca, 10)
        classed(C10, c_bins[:-1] + [np.nanmax(C10[mask]) + 0.01], c_cols,
                f"PM2.5 µg/m³ ({yr})\n10×10 km blocks", "fig6_conc_10km.png")
    wpath = inp["cdir"] / "wind_daily.npy"
    if wpath.exists():
        Wa = np.load(wpath).mean(0)
        classed(Wa, [0, 3, 3.5, 4, 4.5, 5, np.nanmax(Wa[mask]) + .01],
                ["#eff3ff", "#c6dbef", "#9ecae1", "#6baed6", "#3182bd", "#08519c"],
                f"Wind speed {yr}, m/s\n(ERA5-Land, annual mean)", "fig2_wind.jpg")
    LAI = lai_for_mode(inp, cfg.lai_mode, cfg)
    if LAI is not None:
        La = np.nanmean(LAI, 0)
        classed(La, [0, 1, 1.5, 2, 2.5, 3, 3.5, np.nanmax(La[mask]) + .01],
                ["#ffffcc", "#d9f0a3", "#addd8e", "#78c679", "#41ab5d", "#238443", "#005a32"],
                f"LAI {yr}, m²/m²\n(annual mean)", "fig3_lai.jpg")
    classed(dep_main, [0, 0.002, 0.003, 0.004, 0.006, 0.009, np.nanmax(dep_main) + 1e-4],
            ["#1a9641", "#a6d96a", "#ffffbf", "#fdae61", "#f46d43", "#d7191c"],
            f"PM2.5 dep, tonnes/\nkm²/year ({yr})", "fig4_dep.png", fmt="{:.3f}")
    # ecosystem extent map (overview level of the 10 m raster)
    with rasterio.open(cfg.ecosystem_extent_path) as s:
        f = 16
        a = s.read(1, out_shape=(s.height // f, s.width // f))
        tr = s.transform * s.transform.scale(s.width / a.shape[1], s.height / a.shape[0])
    a = np.ma.masked_outside(a, 1, 30)
    e2 = [tr.c, tr.c + tr.a * a.shape[1], tr.f + tr.e * a.shape[0], tr.f]
    fig, ax = base()
    ax.imshow(a, extent=e2, cmap=ListedColormap(STAT_COLOURS), norm=BoundaryNorm(np.arange(.5, 31), 30),
              interpolation="nearest")
    cty.boundary.plot(ax=ax, color="0.3", lw=0.3)
    leg = ax.legend([Patch(fc=c) for c in STAT_COLOURS], [f"{i + 1} {n}" for i, n in enumerate(STAT_SHORT)],
                    loc="upper left", bbox_to_anchor=(e2[1] + 6000, e2[3] - 40000), bbox_transform=ax.transData,
                    fontsize=6.6, title="Ecosystem type level 2\n(Statistics Estonia)", title_fontsize=7.5,
                    frameon=False, alignment="left")
    finalize(fig, ax, (e2[0], e2[2], e2[1], e2[3]), leg, "fig5_eco.png", sb_h=18000)
    fig.savefig(out / "fig5_eco.png", dpi=160); plt.close(fig)
    json.dump(ratios, open(out / "ratios.json", "w"), indent=1)
    log.info("figures written to %s", out)
    return ratios
