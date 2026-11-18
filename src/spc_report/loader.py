"""Load every Excel file in a folder and merge into one validated DataFrame."""

from __future__ import annotations

import warnings
from pathlib import Path

import pandas as pd

from . import config as C


def load_folder(folder: Path) -> pd.DataFrame:
    files = sorted(p for p in Path(folder).glob("*.xlsx") if not p.name.startswith("~$"))
    if not files:
        raise FileNotFoundError(f"No .xlsx files found in {folder}")

    frames = []
    for path in files:
        df = pd.read_excel(path)
        missing = set(C.REQUIRED_COLUMNS) - set(df.columns)
        if missing:
            warnings.warn(f"{path.name}: missing columns {sorted(missing)} - skipped")
            continue
        df["source_file"] = path.name
        frames.append(df)

    if not frames:
        raise ValueError("No valid files to load")

    data = pd.concat(frames, ignore_index=True)
    return clean(data)


def clean(data: pd.DataFrame) -> pd.DataFrame:
    """Coerce types and drop rows that cannot be used."""
    data = data.copy()
    data[C.COL_DATE] = pd.to_datetime(data[C.COL_DATE], errors="coerce")
    data[C.COL_THICK] = pd.to_numeric(data[C.COL_THICK], errors="coerce")
    bad = data[C.REQUIRED_COLUMNS].isna().any(axis=1)
    if bad.any():
        warnings.warn(f"Dropped {int(bad.sum())} rows with missing/non-numeric values")
    data = data[~bad]
    return data.sort_values([C.COL_EQUIP, C.COL_DATE, C.COL_LOT, C.COL_WAFER, C.COL_SITE]).reset_index(
        drop=True
    )
