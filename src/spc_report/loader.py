"""Load every Excel file under a folder (recursively) and merge into one DataFrame."""

from __future__ import annotations

import warnings
from pathlib import Path

import pandas as pd

from . import config as C


def load_folder(folder: Path) -> pd.DataFrame:
    files = sorted(p for p in Path(folder).rglob("*.xlsx") if not p.name.startswith("~$"))
    if not files:
        raise FileNotFoundError(f"No .xlsx files found in {folder}")

    frames = []
    for path in files:
        df = pd.read_excel(path)
        missing = set(C.REQUIRED_COLUMNS) - set(df.columns)
        if missing:
            warnings.warn(f"{path.name}: missing columns {sorted(missing)} - skipped")
            continue
        df["source_file"] = path.relative_to(folder).as_posix()
        frames.append(df)

    if not frames:
        raise ValueError("No valid files to load")
    return clean(pd.concat(frames, ignore_index=True))


def clean(data: pd.DataFrame) -> pd.DataFrame:
    """Coerce types and drop rows that cannot be used."""
    data = data.copy()
    data[C.COL_DATE] = pd.to_datetime(data[C.COL_DATE], errors="coerce")
    data[C.COL_VALUE] = pd.to_numeric(data[C.COL_VALUE], errors="coerce")
    for col in (C.COL_STEP, C.COL_EQUIP, C.COL_LOT, C.COL_WAFER_UID, C.COL_PARAM, C.COL_UNIT):
        data[col] = data[col].astype(str)
    bad = data[C.REQUIRED_COLUMNS].isna().any(axis=1)
    if bad.any():
        warnings.warn(f"Dropped {int(bad.sum())} rows with missing/non-numeric values")
    data = data[~bad]
    keys = [C.COL_STEP, C.COL_EQUIP, C.COL_DATE, C.COL_LOT, C.COL_WAFER, C.COL_SITE]
    return data.sort_values(keys).reset_index(drop=True)
