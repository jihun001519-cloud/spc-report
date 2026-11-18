"""Generate synthetic multi-step measurement data driven by the process flow.

Every lot starts at OX and visits each step in order (step k on day start + k).
The same lot_id / wafer_id (wafer_uid) appears in every step, so wafers can be
traced across the whole flow.

True wafer mean at a step:
    target + tool offset + lot bias + wafer noise
    + sum(coef * (upstream TRUE mean - upstream target))   <- propagation
    + anomalies (shift / spike)
Measured sites = true wafer mean + site noise (tool sigma).
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C
from .flow import Flow, load_flow


def generate_dataframe(flow: Flow | None = None, n_days: int = 10, seed: int = 42) -> pd.DataFrame:
    """Return long-format data: one row per (wafer, step, site)."""
    flow = flow or load_flow()
    rng = np.random.default_rng(seed)
    incoming = {s.id: [p for p in flow.propagation if p.dst == s.id] for s in flow.steps}
    rows: list[dict] = []
    lot_seq = 1

    for day in range(n_days):
        lot_start = flow.start_date + timedelta(days=day)
        for _ in range(flow.lots_per_day):
            lot_id = f"LOT{lot_start:%y%m}{lot_seq:03d}"
            lot_seq += 1
            # deviation of each wafer's TRUE mean from target, per step (for propagation)
            dev: dict[str, np.ndarray] = {}
            for k, step in enumerate(flow.steps):
                step_date = lot_start + timedelta(days=k)
                step_day = (step_date - flow.start_date).days
                tool = step.equipment[rng.integers(len(step.equipment))]
                lot_bias = rng.normal(0, step.sigma_lot)

                n_w = flow.wafers_per_lot
                true = (step.target + tool.offset + lot_bias
                        + rng.normal(0, step.sigma_wafer, n_w))
                for p in incoming[step.id]:
                    true = true + p.coef * dev[p.src]
                for a in flow.anomalies:
                    if a.step not in ("*", step.id) or (a.equipment and a.equipment != tool.id):
                        continue
                    if a.type == "shift" and step_day >= a.from_day:
                        true = true + a.amount
                    elif a.type == "spike":
                        hit = rng.random(n_w) < a.prob
                        sign = rng.choice([-1.0, 1.0], n_w)
                        true = true + hit * sign * a.size * tool.sigma
                dev[step.id] = true - step.target

                for w in range(n_w):
                    sites = rng.normal(true[w], tool.sigma, step.sites)
                    for site_no, value in enumerate(sites, start=1):
                        rows.append({
                            C.COL_DATE: pd.Timestamp(step_date),
                            C.COL_LOT: lot_id,
                            C.COL_WAFER: w + 1,
                            C.COL_WAFER_UID: f"{lot_id}-W{w + 1:02d}",
                            C.COL_STEP: step.id,
                            C.COL_EQUIP: tool.id,
                            C.COL_SITE: site_no,
                            C.COL_PARAM: step.parameter,
                            C.COL_UNIT: step.unit,
                            C.COL_VALUE: round(float(value), 3),
                        })
    return pd.DataFrame(rows, columns=C.REQUIRED_COLUMNS)


def write_files(df: pd.DataFrame, out_dir: Path) -> list[Path]:
    """Write data/<STEP>/<STEP>_<YYYY-MM-DD>.xlsx (one file per step per day)."""
    paths = []
    for (step, d), part in df.groupby([C.COL_STEP, C.COL_DATE], sort=True):
        folder = Path(out_dir) / str(step)
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{step}_{d:%Y-%m-%d}.xlsx"
        part.to_excel(path, index=False)
        paths.append(path)
    return paths


def generate(out_dir: Path, n_days: int = 10, seed: int = 42, flow: Flow | None = None) -> list[Path]:
    return write_files(generate_dataframe(flow, n_days=n_days, seed=seed), out_dir)
