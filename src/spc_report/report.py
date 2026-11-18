"""Assemble the final Excel report (openpyxl).

Sheets:
  Summary     - per (step, tool) statistics + control limits + OOC counts
  Flow        - process flow, injected propagation (ground truth), anomalies
  <STEP> ...  - one sheet per step: X-bar/R chart per tool + subgroup table
  WaferTrace  - one row per wafer, tool + mean per step (input for propagation analysis)
  OOC_List    - every out-of-control subgroup
  RawData     - merged raw measurements
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from . import config as C
from .chart import draw_xbar_r, fmt_value
from .flow import Flow, load_flow
from .loader import load_folder
from .stats import (ChartResult, control_charts, equipment_summary, ooc_table, ordered_steps,
                    phase1_cutoff, wafer_trace)

HEADER_FILL = PatternFill("solid", fgColor="1F3A5F")
HEADER_FONT = Font(bold=True, color="FFFFFF")
OOC_FILL = PatternFill("solid", fgColor="F8D7DA")
OOC_FONT = Font(color="9B1C1C", bold=True)
THIN = Side(style="thin", color="BFBFBF")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
BOLD = Font(bold=True)
NOTE = Font(italic=True, color="666666")

IMG_SCALE = 0.8
ROWS_PER_CHART = 32   # ~ (715 px * 0.8) / 20 px per row, plus a little margin


def _write_table(ws: Worksheet, df: pd.DataFrame, start_row: int = 1, start_col: int = 1,
                 number_format: str = "0.000") -> None:
    for j, col in enumerate(df.columns):
        c = ws.cell(row=start_row, column=start_col + j, value=str(col))
        c.fill, c.font, c.border = HEADER_FILL, HEADER_FONT, BORDER
        c.alignment = Alignment(horizontal="center")
    for i, row in enumerate(df.itertuples(index=False), start=1):
        for j, val in enumerate(row):
            if isinstance(val, pd.Timestamp):
                val = val.to_pydatetime()
            elif val is pd.NaT or (isinstance(val, float) and pd.isna(val)):
                val = None  # empty cell instead of "nan"
            c = ws.cell(row=start_row + i, column=start_col + j, value=val)
            c.border = BORDER
            if isinstance(val, float):
                c.number_format = number_format
            elif hasattr(val, "year"):
                c.number_format = "yyyy-mm-dd"


def _highlight_rows(ws: Worksheet, df: pd.DataFrame, start_row: int) -> None:
    """Pink rows where xbar_ooc / r_ooc is True; red font on the offending value."""
    cols = list(df.columns)
    xi, ri = cols.index("xbar") + 1, cols.index("range") + 1
    for i, rec in enumerate(df[["xbar_ooc", "r_ooc"]].itertuples(index=False), start=1):
        if not (rec.xbar_ooc or rec.r_ooc):
            continue
        r = start_row + i
        for j in range(1, len(cols) + 1):
            ws.cell(row=r, column=j).fill = OOC_FILL
        if rec.xbar_ooc:
            ws.cell(row=r, column=xi).font = OOC_FONT
        if rec.r_ooc:
            ws.cell(row=r, column=ri).font = OOC_FONT


def _autofit(ws: Worksheet, min_width: int = 8, max_width: int = 30) -> None:
    widths: dict[int, int] = {}
    for row in ws.iter_rows():
        for c in row:
            if c.value is not None:
                widths[c.column] = max(widths.get(c.column, 0), len(str(c.value)))
    for col, w in widths.items():
        ws.column_dimensions[get_column_letter(col)].width = max(min_width, min(max_width, w + 2))


def _title(ws: Worksheet, text: str, note: str | None = None) -> None:
    ws["A1"] = text
    ws["A1"].font = Font(bold=True, size=14)
    if note:
        ws["A2"] = note
        ws["A2"].font = NOTE


# ---------------------------------------------------------------- sheets

def _summary_sheet(ws: Worksheet, summary: pd.DataFrame, results: list[ChartResult],
                   n_files: int, phase_note: str) -> None:
    _title(ws, "SPC Report - STI process flow", f"Source files: {n_files}   |   "
           "Subgroup: 1 wafer at 1 step (n = measurement sites)")
    ws["A3"], ws["A3"].font = phase_note, NOTE

    ws["A5"], ws["A5"].font = "1. Step / equipment summary (all measurements)", BOLD
    _write_table(ws, summary.rename(columns={C.COL_EQUIP: "equipment"}), start_row=6)

    row = 6 + len(summary) + 3
    ws.cell(row=row, column=1, value="2. Control limits (X-bar / R, from Phase I)").font = BOLD
    limits = pd.DataFrame([
        {
            "step": r.step,
            "equipment": r.equipment,
            "Phase I SG": int((r.subgroups["phase"] == "I").sum()),
            "Phase II SG": int((r.subgroups["phase"] == "II").sum()),
            "X-dbar (CL)": r.limits.xbar_cl,
            "X UCL": r.limits.xbar_ucl,
            "X LCL": r.limits.xbar_lcl,
            "R-bar (CL)": r.limits.r_cl,
            "R UCL": r.limits.r_ucl,
            "R LCL": r.limits.r_lcl,
            "X-bar OOC": int(r.subgroups["xbar_ooc"].sum()),
            "R OOC": int(r.subgroups["r_ooc"].sum()),
        }
        for r in results
    ])
    _write_table(ws, limits, start_row=row + 1)
    for j in (limits.columns.get_loc("X-bar OOC") + 1, limits.columns.get_loc("R OOC") + 1):
        for i in range(len(limits)):
            c = ws.cell(row=row + 2 + i, column=j)
            if c.value:
                c.fill, c.font = OOC_FILL, OOC_FONT
    _autofit(ws)
    ws.column_dimensions["A"].width = 12


def _flow_sheet(ws: Worksheet, flow: Flow) -> None:
    _title(ws, "Process flow (simplified STI)",
           "Synthetic data: all values are educational assumptions, not real fab data.")
    steps = pd.DataFrame([
        {"order": i + 1, "step": s.id, "name": s.name, "parameter": s.parameter, "unit": s.unit,
         "target": s.target, "LSL": s.lsl, "USL": s.usl, "sites (n)": s.sites,
         "sigma_lot": s.sigma_lot, "sigma_wafer": s.sigma_wafer,
         "equipment": ", ".join(f"{e.id}(off {e.offset:+g}, s {e.sigma:g})" for e in s.equipment)}
        for i, s in enumerate(flow.steps)
    ])
    ws["A4"], ws["A4"].font = "1. Steps (in process order)", BOLD
    _write_table(ws, steps, start_row=5)

    row = 5 + len(steps) + 3
    ws.cell(row=row, column=1,
            value="2. Inter-step propagation injected by the generator (GROUND TRUTH)").font = BOLD
    ws.cell(row=row + 1, column=1,
            value="dst wafer mean += coef x (src wafer true mean - src target)").font = NOTE
    props = pd.DataFrame([{"from": p.src, "to": p.dst, "coef": p.coef, "note": p.note}
                          for p in flow.propagation], columns=["from", "to", "coef", "note"])
    _write_table(ws, props, start_row=row + 2)

    row = row + 2 + len(props) + 3
    ws.cell(row=row, column=1, value="3. Injected anomalies").font = BOLD
    anomalies = pd.DataFrame([
        {"type": a.type, "step": a.step, "equipment": a.equipment or "*",
         "detail": (f"+{a.amount:g} {('from day ' + str(a.from_day))}" if a.type == "shift"
                    else f"prob {a.prob:g}, +/-{a.size:g} x tool sigma")}
        for a in flow.anomalies
    ], columns=["type", "step", "equipment", "detail"])
    _write_table(ws, anomalies, start_row=row + 1)
    _autofit(ws, max_width=60)


def _step_sheet(ws: Worksheet, step: str, results: list[ChartResult], images: dict) -> None:
    first = results[0]
    _title(ws, f"{step} - {first.parameter} ({first.unit})  X-bar / R control charts")
    row = 3
    for r in results:
        lim = r.limits
        ws.cell(row=row, column=1, value=(
            f"{r.equipment}:  X  CL={fmt_value(lim.xbar_cl)}  UCL={fmt_value(lim.xbar_ucl)}  "
            f"LCL={fmt_value(lim.xbar_lcl)}   |   R  CL={fmt_value(lim.r_cl)}  "
            f"UCL={fmt_value(lim.r_ucl)}  LCL={fmt_value(lim.r_lcl)}")).font = BOLD
        img = XLImage(str(images[(r.step, r.equipment)]))
        img.width, img.height = img.width * IMG_SCALE, img.height * IMG_SCALE
        ws.add_image(img, f"A{row + 1}")
        row += ROWS_PER_CHART

    ws.cell(row=row, column=1, value="Subgroups (one row per wafer)").font = BOLD
    table = pd.concat([r.subgroups for r in results], ignore_index=True)
    table = table[["subgroup", "phase", C.COL_EQUIP, C.COL_DATE, C.COL_LOT, C.COL_WAFER,
                   C.COL_WAFER_UID, "n", "xbar", "range", "xbar_ooc", "r_ooc"]]
    _write_table(ws, table, start_row=row + 1)
    _highlight_rows(ws, table, start_row=row + 1)
    _autofit(ws)
    ws.column_dimensions["A"].width = 10


# ---------------------------------------------------------------- main

def build_report(data_dir: Path, out_path: Path,
                 phase1_days: int | None = C.DEFAULT_PHASE1_DAYS,
                 flow: Flow | None = None) -> dict:
    flow = flow or load_flow()
    data = load_folder(data_dir)
    steps = ordered_steps(data, flow.step_ids)
    summary = equipment_summary(data, steps)
    results = control_charts(data, phase1_days, steps)
    ooc = ooc_table(results)
    trace = wafer_trace(data, steps)

    if not phase1_days or phase1_days <= 0:
        phase_note = "Control limits: all data (Phase I only)"
    else:
        phase_note = (f"Control limits from Phase I = first {phase1_days} days of each step; "
                      "later data monitored as Phase II")

    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"
    _summary_sheet(ws, summary, results, data["source_file"].nunique(), phase_note)
    _flow_sheet(wb.create_sheet("Flow"), flow)

    out_path = Path(out_path)
    with tempfile.TemporaryDirectory() as tmp:
        images = {(r.step, r.equipment): draw_xbar_r(r, Path(tmp) / f"{r.step}_{r.equipment}.png")
                  for r in results}
        for step in steps:
            _step_sheet(wb.create_sheet(step[:31]), step,
                        [r for r in results if r.step == step], images)

        ws = wb.create_sheet("WaferTrace")
        _write_table(ws, trace)
        ws.freeze_panes = "B2"
        _autofit(ws)

        ws = wb.create_sheet("OOC_List")
        if ooc.empty:
            ws["A1"] = "No out-of-control subgroups."
        else:
            _write_table(ws, ooc)
            ws.freeze_panes = "A2"
            _autofit(ws)

        ws = wb.create_sheet("RawData")
        _write_table(ws, data)
        ws.freeze_panes = "A2"
        _autofit(ws)

        out_path.parent.mkdir(parents=True, exist_ok=True)
        wb.save(out_path)  # images are read at save time, so save inside the tempdir block

    return {
        "rows": len(data),
        "files": int(data["source_file"].nunique()),
        "steps": len(steps),
        "charts": len(results),
        "wafers": len(trace),
        "ooc": len(ooc),
        "path": out_path,
    }
