"""Summary statistics and X-bar / R control chart calculations.

Subgroup = one wafer (n = SITES_PER_WAFER measurement sites).

    X-bar chart:  CL = X-double-bar,  UCL/LCL = X-double-bar +/- A2 * R-bar
    R chart:      CL = R-bar,         UCL = D4 * R-bar,  LCL = D3 * R-bar
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from . import config as C


@dataclass
class ControlLimits:
    n: int
    xbar_cl: float
    xbar_ucl: float
    xbar_lcl: float
    r_cl: float
    r_ucl: float
    r_lcl: float


@dataclass
class ChartResult:
    equipment: str
    limits: ControlLimits
    subgroups: pd.DataFrame  # one row per wafer: xbar, range, OOC flags


def equipment_summary(data: pd.DataFrame) -> pd.DataFrame:
    """Mean / std / min / max per tool, over all individual measurements."""
    g = data.groupby(C.COL_EQUIP)[C.COL_THICK]
    out = pd.DataFrame(
        {
            "N": g.count(),
            "Mean": g.mean(),
            "StdDev": g.std(ddof=1),
            "Min": g.min(),
            "Max": g.max(),
        }
    )
    out["Range"] = out["Max"] - out["Min"]
    return out.reset_index()


def make_subgroups(data: pd.DataFrame) -> pd.DataFrame:
    """Collapse site-level rows into one row per wafer (subgroup)."""
    keys = [C.COL_EQUIP, C.COL_DATE, C.COL_LOT, C.COL_WAFER]
    g = data.groupby(keys, sort=True)[C.COL_THICK]
    sub = pd.DataFrame({"n": g.count(), "xbar": g.mean(), "range": g.max() - g.min()}).reset_index()
    return sub


def compute_limits(sub: pd.DataFrame) -> ControlLimits:
    n = int(sub["n"].mode().iloc[0])
    if n not in C.SPC_CONSTANTS:
        raise ValueError(f"No SPC constants for subgroup size n={n}")
    k = C.SPC_CONSTANTS[n]
    xbb = float(sub["xbar"].mean())
    rbar = float(sub["range"].mean())
    return ControlLimits(
        n=n,
        xbar_cl=xbb,
        xbar_ucl=xbb + k["A2"] * rbar,
        xbar_lcl=xbb - k["A2"] * rbar,
        r_cl=rbar,
        r_ucl=k["D4"] * rbar,
        r_lcl=k["D3"] * rbar,
    )


def flag_ooc(sub: pd.DataFrame, lim: ControlLimits) -> pd.DataFrame:
    sub = sub.copy()
    sub["xbar_ooc"] = (sub["xbar"] > lim.xbar_ucl) | (sub["xbar"] < lim.xbar_lcl)
    sub["r_ooc"] = (sub["range"] > lim.r_ucl) | (sub["range"] < lim.r_lcl)
    return sub


def control_charts(data: pd.DataFrame) -> list[ChartResult]:
    """One X-bar/R chart per equipment (tools have different means)."""
    results = []
    all_sub = make_subgroups(data)
    for equip, sub in all_sub.groupby(C.COL_EQUIP, sort=True):
        sub = sub.reset_index(drop=True)
        lim = compute_limits(sub)
        sub = flag_ooc(sub, lim)
        sub.insert(0, "subgroup", range(1, len(sub) + 1))
        results.append(ChartResult(equipment=str(equip), limits=lim, subgroups=sub))
    return results


def ooc_table(results: list[ChartResult]) -> pd.DataFrame:
    """All out-of-control subgroups across tools, with the reason."""
    frames = []
    for r in results:
        s = r.subgroups
        hit = s[s["xbar_ooc"] | s["r_ooc"]].copy()
        if hit.empty:
            continue
        hit["reason"] = hit.apply(
            lambda row: ", ".join(
                name for name, flag in (("X-bar", row["xbar_ooc"]), ("R", row["r_ooc"])) if flag
            ),
            axis=1,
        )
        frames.append(hit)
    cols = ["subgroup", C.COL_EQUIP, C.COL_DATE, C.COL_LOT, C.COL_WAFER, "xbar", "range", "reason"]
    if not frames:
        return pd.DataFrame(columns=cols)
    return pd.concat(frames, ignore_index=True)[cols]
