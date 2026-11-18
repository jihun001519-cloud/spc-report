"""Shared constants: column names, default paths, SPC constants."""

from pathlib import Path

# ---- Column names (single source of truth for every module) ----
COL_DATE = "date"
COL_LOT = "lot_id"
COL_WAFER = "wafer_id"
COL_EQUIP = "equipment_id"
COL_SITE = "site"
COL_THICK = "thickness_nm"

REQUIRED_COLUMNS = [COL_DATE, COL_LOT, COL_WAFER, COL_EQUIP, COL_SITE, COL_THICK]

# ---- Default paths ----
DEFAULT_DATA_DIR = Path("data")
DEFAULT_REPORT_PATH = Path("output") / "spc_report.xlsx"

# ---- Process settings for synthetic data ----
DEFAULT_PHASE1_DAYS = 5      # first N days set the control limits (Phase I)

TARGET_THICKNESS_NM = 1000.0
SITES_PER_WAFER = 5          # subgroup size n
WAFERS_PER_LOT = 25

# Each tool has its own slightly different mean offset and spread (nm).
EQUIPMENT_PROFILES = {
    "CVD-01": {"offset": 0.0, "sigma": 4.0},
    "CVD-02": {"offset": 3.0, "sigma": 5.0},
    "CVD-03": {"offset": -2.0, "sigma": 3.5},
    "CVD-04": {"offset": 1.0, "sigma": 6.0},
}

# ---- X-bar / R chart constants for subgroup size n ----
# Source: standard SPC tables (e.g. Montgomery, Appendix VI).
SPC_CONSTANTS = {
    2: {"A2": 1.880, "D3": 0.0, "D4": 3.267},
    3: {"A2": 1.023, "D3": 0.0, "D4": 2.574},
    4: {"A2": 0.729, "D3": 0.0, "D4": 2.282},
    5: {"A2": 0.577, "D3": 0.0, "D4": 2.114},
    6: {"A2": 0.483, "D3": 0.0, "D4": 2.004},
}
