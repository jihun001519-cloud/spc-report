"""Summary statistics and X-bar / R control chart calculations.

Subgroup = one wafer at one step (n = sites measured on that wafer).
Charts are built per (step, equipment).

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
    step: str
    equipment: str
    parameter: str
    unit: str
    limits: ControlLimits
    subgroups: pd.DataFrame  # one row per wafer: phase, xbar, range, OOC flags


def ordered_steps(data: pd.DataFrame, step_order: list[str] | None = None) -> list[str]:
    """Steps in flow order; steps missing from the flow go last (alphabetically)."""
    present = list(dict.fromkeys(sorted(data[C.COL_STEP].unique())))
    order = [s for s in (step_order or []) if s in present]
    return order + [s for s in present if s not in order]


def equipment_summary(data: pd.DataFrame, step_order: list[str] | None = None) -> pd.DataFrame:
    """Mean / std / min / max per (step, tool), over all individual measurements."""
    keys = [C.COL_STEP, C.COL_PARAM, C.COL_UNIT, C.COL_EQUIP]
    g = data.groupby(keys)[C.COL_VALUE]
    out = pd.DataFrame({"N": g.count(), "Mean": g.mean(), "StdDev": g.std(ddof=1),
                        "Min": g.min(), "Max": g.max()})
    out["Range"] = out["Max"] - out["Min"]
    out = out.reset_index()
    rank = {s: i for i, s in enumerate(ordered_steps(data, step_order))}
    return (out.assign(_r=out[C.COL_STEP].map(rank))
               .sort_values(["_r", C.COL_EQUIP]).drop(columns="_r").reset_index(drop=True))


def make_subgroups(data: pd.DataFrame) -> pd.DataFrame:
    """Collapse site-level rows into one row per wafer per step (subgroup)."""
    keys = [C.COL_STEP, C.COL_EQUIP, C.COL_DATE, C.COL_LOT, C.COL_WAFER, C.COL_WAFER_UID]
    g = data.groupby(keys, sort=True)[C.COL_VALUE]
    return pd.DataFrame({"n": g.count(), "xbar": g.mean(), "range": g.max() - g.min()}).reset_index()


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


def phase1_cutoff(dates: pd.Series, phase1_days: int | None) -> pd.Timestamp | None:
    """First date of Phase II, or None when every row is Phase I."""
    if not phase1_days or phase1_days <= 0:
        return None
    cutoff = pd.Timestamp(dates.min()).normalize() + pd.Timedelta(days=phase1_days)
    return cutoff if dates.max() >= cutoff else None


def control_charts(data: pd.DataFrame, phase1_days: int | None = C.DEFAULT_PHASE1_DAYS,
                   step_order: list[str] | None = None) -> list[ChartResult]:
    """One X-bar/R chart per (step, equipment).

    Phase I  = the first `phase1_days` days *of each step*: sets the control limits.
    Phase II = everything after: monitored against the Phase I limits.
    phase1_days=None/0 uses all data as Phase I.
    """
    results = []
    all_sub = make_subgroups(data)
    meta = data.groupby(C.COL_STEP)[[C.COL_PARAM, C.COL_UNIT]].first()
    for step in ordered_steps(data, step_order):
        step_sub = all_sub[all_sub[C.COL_STEP] == step]
        cutoff = phase1_cutoff(step_sub[C.COL_DATE], phase1_days)
        for equip, sub in step_sub.groupby(C.COL_EQUIP, sort=True):
            sub = sub.reset_index(drop=True)
            if cutoff is None:
                is_p1 = pd.Series(True, index=sub.index)
            else:
                is_p1 = sub[C.COL_DATE] < cutoff
            if not is_p1.any():
                raise ValueError(f"{step}/{equip}: no Phase I data in the first {phase1_days} days")
            lim = compute_limits(sub[is_p1])
            sub = flag_ooc(sub, lim)
            sub.insert(0, "phase", is_p1.map({True: "I", False: "II"}))
            sub.insert(0, "subgroup", range(1, len(sub) + 1))
            results.append(ChartResult(step=step, equipment=str(equip),
                                       parameter=meta.loc[step, C.COL_PARAM],
                                       unit=meta.loc[step, C.COL_UNIT],
                                       limits=lim, subgroups=sub))
    return results


def ooc_table(results: list[ChartResult]) -> pd.DataFrame:
    """All out-of-control subgroups across steps and tools, with the reason."""
    cols = ["subgroup", "phase", C.COL_STEP, C.COL_EQUIP, C.COL_DATE, C.COL_LOT, C.COL_WAFER,
            C.COL_WAFER_UID, "xbar", "range", "reason"]
    frames = []
    for r in results:
        s = r.subgroups
        hit = s[s["xbar_ooc"] | s["r_ooc"]].copy()
        if hit.empty:
            continue
        hit["reason"] = [
            ", ".join(n for n, f in (("X-bar", x), ("R", rr)) if f)
            for x, rr in zip(hit["xbar_ooc"], hit["r_ooc"])
        ]
        frames.append(hit)
    if not frames:
        return pd.DataFrame(columns=cols)
    return pd.concat(frames, ignore_index=True)[cols]


def wafer_trace(data: pd.DataFrame, step_order: list[str] | None = None) -> pd.DataFrame:
    """One row per wafer; per step: the tool used and the wafer mean.

    Columns: wafer_uid, lot_id, wafer_id, then <STEP>_equipment, <STEP>_<parameter> ...
    This is the input for inter-step (propagation) analysis.
    """
    sub = make_subgroups(data)
    params = data.groupby(C.COL_STEP)[C.COL_PARAM].first()
    base = (sub[[C.COL_WAFER_UID, C.COL_LOT, C.COL_WAFER]]
            .drop_duplicates(C.COL_WAFER_UID).set_index(C.COL_WAFER_UID))
    cols = []
    for step in ordered_steps(data, step_order):
        s = sub[sub[C.COL_STEP] == step].set_index(C.COL_WAFER_UID)
        cols.append(s[C.COL_EQUIP].rename(f"{step}_equipment"))
        cols.append(s["xbar"].rename(f"{step}_{params[step]}"))
    out = base.join(pd.concat(cols, axis=1))
    return out.reset_index().sort_values([C.COL_LOT, C.COL_WAFER]).reset_index(drop=True)
