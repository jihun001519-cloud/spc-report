"""Shared constants: column names, default paths, SPC constants.

Process-specific settings (steps, tools, targets) live in process_flow.toml.
"""

from pathlib import Path

# ---- Column names (single source of truth for every module) ----
COL_DATE = "date"
COL_LOT = "lot_id"
COL_WAFER = "wafer_id"
COL_WAFER_UID = "wafer_uid"     # "<lot_id>-W<wafer>": links one wafer across all steps
COL_STEP = "step"
COL_EQUIP = "equipment_id"
COL_SITE = "site"
COL_PARAM = "parameter"
COL_UNIT = "unit"
COL_VALUE = "value"

REQUIRED_COLUMNS = [COL_DATE, COL_LOT, COL_WAFER, COL_WAFER_UID, COL_STEP, COL_EQUIP,
                    COL_SITE, COL_PARAM, COL_UNIT, COL_VALUE]

# ---- Default paths ----
DEFAULT_DATA_DIR = Path("data")
DEFAULT_REPORT_PATH = Path("output") / "spc_report.xlsx"

DEFAULT_PHASE1_DAYS = 5      # first N days of each step set the control limits (Phase I)

# ---- X-bar / R chart constants for subgroup size n ----
# Source: standard SPC tables (e.g. Montgomery, Appendix VI).
SPC_CONSTANTS = {
    2: {"A2": 1.880, "D3": 0.0, "D4": 3.267},
    3: {"A2": 1.023, "D3": 0.0, "D4": 2.574},
    4: {"A2": 0.729, "D3": 0.0, "D4": 2.282},
    5: {"A2": 0.577, "D3": 0.0, "D4": 2.114},
    6: {"A2": 0.483, "D3": 0.0, "D4": 2.004},
}
