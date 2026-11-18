"""Draw X-bar / R control charts as PNG images (matplotlib)."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless backend: no GUI window needed
import matplotlib.pyplot as plt

from .stats import ChartResult

NORMAL = "#2b6cb0"
OOC = "#d62828"
LIMIT = "#c05621"
CENTER = "#2f855a"


def _panel(ax, x, y, ooc, cl, ucl, lcl, ylabel, fmt):
    ax.plot(x, y, color=NORMAL, marker="o", markersize=3.5, linewidth=1, zorder=2)
    ax.scatter(x[ooc], y[ooc], color=OOC, s=45, zorder=3, edgecolor="white", linewidth=0.8,
               label="Out of control")
    ax.axhline(cl, color=CENTER, linewidth=1.2)
    ax.axhline(ucl, color=LIMIT, linestyle="--", linewidth=1.2)
    ax.axhline(lcl, color=LIMIT, linestyle="--", linewidth=1.2)
    right = x.max() + 0.5
    for val, name, color in ((ucl, "UCL", LIMIT), (cl, "CL", CENTER), (lcl, "LCL", LIMIT)):
        ax.text(right, val, f" {name}={val:{fmt}}", va="center", fontsize=8, color=color)
    ax.set_ylabel(ylabel)
    ax.grid(alpha=0.25)
    ax.spines[["top", "right"]].set_visible(False)
    if ooc.any():
        ax.legend(loc="upper left", fontsize=8, frameon=False)


def draw_xbar_r(result: ChartResult, out_path: Path) -> Path:
    s, lim = result.subgroups, result.limits
    x = s["subgroup"].to_numpy()

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 6.5), sharex=True,
                                   gridspec_kw={"height_ratios": [3, 2]})
    _panel(ax1, x, s["xbar"].to_numpy(), s["xbar_ooc"].to_numpy(),
           lim.xbar_cl, lim.xbar_ucl, lim.xbar_lcl, "X-bar (nm)", ".2f")
    _panel(ax2, x, s["range"].to_numpy(), s["r_ooc"].to_numpy(),
           lim.r_cl, lim.r_ucl, lim.r_lcl, "Range (nm)", ".2f")

    # Phase I / Phase II boundary (only when both phases exist)
    if "phase" in s and (s["phase"] == "II").any() and (s["phase"] == "I").any():
        boundary = s.loc[s["phase"] == "II", "subgroup"].min() - 0.5
        for ax in (ax1, ax2):
            ax.axvline(boundary, color="#555555", linestyle=":", linewidth=1.3)
        top = ax1.get_ylim()[1]
        ax1.text(boundary - 0.8, top, "Phase I (limits set)", ha="right", va="top", fontsize=8,
                 color="#555555")
        ax1.text(boundary + 0.8, top, "Phase II (monitoring)", ha="left", va="top", fontsize=8,
                 color="#555555")

    n_x, n_r = int(s["xbar_ooc"].sum()), int(s["r_ooc"].sum())
    ax1.set_title(f"{result.equipment}  X-bar chart  (n={lim.n}, OOC={n_x})", loc="left", fontsize=11)
    ax2.set_title(f"{result.equipment}  R chart  (OOC={n_r})", loc="left", fontsize=11)
    ax2.set_xlabel("Subgroup (wafer, time order)")

    fig.tight_layout()
    fig.subplots_adjust(right=0.88)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=110)
    plt.close(fig)
    return out_path
