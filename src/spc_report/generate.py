"""Generate synthetic thin-film thickness measurement data as multiple Excel files.

Layout: one Excel file per day. Each day, every tool processes one LOT;
each LOT has several wafers; each wafer is measured at SITES_PER_WAFER sites.

Injected anomalies (so the control charts have something to catch):
  * spikes      - a few random wafers get a +/- 6 sigma jump
  * mean shift  - one tool drifts upward from a given day onward
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C


def generate_dataframe(
    n_days: int = 10,
    wafers_per_lot: int = 8,
    start: date = date(2026, 11, 1),
    seed: int = 42,
    spike_prob: float = 0.02,
    shift_equipment: str = "CVD-02",
    shift_from_day: int = 7,
    shift_nm: float = 12.0,
) -> pd.DataFrame:
    """Return a long-format DataFrame: one row per (wafer, site) measurement."""
    rng = np.random.default_rng(seed)
    rows: list[dict] = []
    lot_seq = 1

    for day in range(n_days):
        d = start + timedelta(days=day)
        for equip, prof in C.EQUIPMENT_PROFILES.items():
            lot_id = f"LOT{d:%y%m}{lot_seq:03d}"
            lot_seq += 1
            # lot-to-lot variation: small random offset shared by the whole lot
            lot_bias = rng.normal(0, prof["sigma"] * 0.3)
            for wafer in range(1, wafers_per_lot + 1):
                mean = C.TARGET_THICKNESS_NM + prof["offset"] + lot_bias
                if equip == shift_equipment and day >= shift_from_day:
                    mean += shift_nm
                # spike: whole wafer jumps (e.g. a bad recipe step)
                if rng.random() < spike_prob:
                    mean += rng.choice([-1, 1]) * 6 * prof["sigma"]
                sites = rng.normal(mean, prof["sigma"], C.SITES_PER_WAFER)
                for site_no, value in enumerate(sites, start=1):
                    rows.append(
                        {
                            C.COL_DATE: pd.Timestamp(d),
                            C.COL_LOT: lot_id,
                            C.COL_WAFER: wafer,
                            C.COL_EQUIP: equip,
                            C.COL_SITE: site_no,
                            C.COL_THICK: round(float(value), 2),
                        }
                    )
    return pd.DataFrame(rows)


def write_daily_files(df: pd.DataFrame, out_dir: Path) -> list[Path]:
    """Split by date and write one Excel file per day."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for d, part in df.groupby(C.COL_DATE):
        path = out_dir / f"measurement_{d:%Y-%m-%d}.xlsx"
        part.to_excel(path, index=False)
        paths.append(path)
    return paths


def generate(out_dir: Path, n_days: int = 10, seed: int = 42, **kwargs) -> list[Path]:
    df = generate_dataframe(n_days=n_days, seed=seed, **kwargs)
    return write_daily_files(df, out_dir)
