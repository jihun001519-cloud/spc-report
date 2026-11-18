"""Assemble the final Excel report (openpyxl).

Sheets:
  Summary       - per-tool mean/std table + control limits + OOC counts
  XbarR_<tool>  - control chart image + subgroup table (OOC rows highlighted)
  OOC_List      - every out-of-control subgroup
  RawData       - merged raw measurements
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
from .chart import draw_xbar_r
from .loader import load_folder
from .stats import ChartResult, control_charts, equipment_summary, ooc_table, phase1_cutoff

HEADER_FILL = PatternFill("solid", fgColor="1F3A5F")
HEADER_FONT = Font(bold=True, color="FFFFFF")
OOC_FILL = PatternFill("solid", fgColor="F8D7DA")
OOC_FONT = Font(color="9B1C1C", bold=True)
THIN = Side(style="thin", color="BFBFBF")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def _write_table(ws: Worksheet, df: pd.DataFrame, start_row: int = 1, start_col: int = 1,
                 number_format: str = "0.00") -> None:
    for j, col in enumerate(df.columns):
        c = ws.cell(row=start_row, column=start_col + j, value=str(col))
        c.fill, c.font, c.border = HEADER_FILL, HEADER_FONT, BORDER
        c.alignment = Alignment(horizontal="center")
    for i, row in enumerate(df.itertuples(index=False), start=1):
        for j, val in enumerate(row):
            if isinstance(val, pd.Timestamp):
                val = val.to_pydatetime()
            c = ws.cell(row=start_row + i, column=start_col + j, value=val)
            c.border = BORDER
            if isinstance(val, float):
                c.number_format = number_format
            elif hasattr(val, "year"):
                c.number_format = "yyyy-mm-dd"


def _autofit(ws: Worksheet, min_width: int = 8, max_width: int = 28) -> None:
    widths: dict[int, int] = {}
    for row in ws.iter_rows():
        for c in row:
            if c.value is not None:
                widths[c.column] = max(widths.get(c.column, 0), len(str(c.value)))
    for col, w in widths.items():
        ws.column_dimensions[get_column_letter(col)].width = max(min_width, min(max_width, w + 2))


def _summary_sheet(ws: Worksheet, summary: pd.DataFrame, results: list[ChartResult],
                   n_files: int, phase_note: str) -> None:
    ws["A1"] = "SPC Report - Film Thickness"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = f"Source files: {n_files}   |   Subgroup: 1 wafer (n={C.SITES_PER_WAFER} sites)"
    ws["A2"].font = Font(italic=True, color="666666")
    ws["A3"] = phase_note
    ws["A3"].font = Font(italic=True, color="666666")

    ws["A4"] = "1. Equipment summary (all measurements)"
    ws["A4"].font = Font(bold=True)
    _write_table(ws, summary.rename(columns={C.COL_EQUIP: "Equipment"}), start_row=5)

    row = 5 + len(summary) + 3
    ws.cell(row=row, column=1, value="2. Control limits (X-bar / R)").font = Font(bold=True)
    limits = pd.DataFrame(
        [
            {
                "Equipment": r.equipment,
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
        ]
    )
    _write_table(ws, limits, start_row=row + 1)
    # highlight non-zero OOC counts
    for i in range(len(limits)):
        for j in (10, 11):
            c = ws.cell(row=row + 2 + i, column=j)
            if c.value:
                c.fill, c.font = OOC_FILL, OOC_FONT
    _autofit(ws)
    ws.column_dimensions["A"].width = 14


def _chart_sheet(ws: Worksheet, result: ChartResult, img_path: Path) -> None:
    lim = result.limits
    ws["A1"] = f"{result.equipment} - X-bar / R control chart"
    ws["A1"].font = Font(bold=True, size=13)
    ws["A2"] = (f"X: CL={lim.xbar_cl:.2f}  UCL={lim.xbar_ucl:.2f}  LCL={lim.xbar_lcl:.2f}    "
                f"R: CL={lim.r_cl:.2f}  UCL={lim.r_ucl:.2f}  LCL={lim.r_lcl:.2f}")
    ws.add_image(XLImage(str(img_path)), "A4")

    table_row = 40  # below the image (~715 px tall)
    s = result.subgroups.rename(columns={C.COL_EQUIP: "equipment"})
    s = s[["subgroup", "phase", C.COL_DATE, C.COL_LOT, C.COL_WAFER, "n", "xbar", "range", "xbar_ooc", "r_ooc"]]
    _write_table(ws, s, start_row=table_row)
    xbar_col, r_col = 7, 8
    for i, rec in enumerate(s.itertuples(index=False), start=1):
        r = table_row + i
        if rec.xbar_ooc or rec.r_ooc:
            for j in range(1, len(s.columns) + 1):
                ws.cell(row=r, column=j).fill = OOC_FILL
            if rec.xbar_ooc:
                ws.cell(row=r, column=xbar_col).font = OOC_FONT
            if rec.r_ooc:
                ws.cell(row=r, column=r_col).font = OOC_FONT
    ws.freeze_panes = ws.cell(row=table_row + 1, column=1)
    _autofit(ws)
    ws.column_dimensions["A"].width = 10


def build_report(data_dir: Path, out_path: Path,
                 phase1_days: int | None = C.DEFAULT_PHASE1_DAYS) -> dict:
    data = load_folder(data_dir)
    summary = equipment_summary(data)
    results = control_charts(data, phase1_days)
    cutoff = phase1_cutoff(data, phase1_days)
    if cutoff is None:
        phase_note = "Control limits: all data (Phase I only)"
    else:
        phase_note = (f"Control limits from Phase I = dates before {cutoff:%Y-%m-%d} "
                      f"(first {phase1_days} days); later data monitored as Phase II")
    ooc = ooc_table(results)

    wb = Workbook()
    _summary_sheet(wb.active, summary, results, n_files=data["source_file"].nunique(),
                   phase_note=phase_note)
    wb.active.title = "Summary"

    with tempfile.TemporaryDirectory() as tmp:
        for r in results:
            img = draw_xbar_r(r, Path(tmp) / f"{r.equipment}.png")
            _chart_sheet(wb.create_sheet(f"XbarR_{r.equipment}"[:31]), r, img)

        ws = wb.create_sheet("OOC_List")
        if ooc.empty:
            ws["A1"] = "No out-of-control subgroups."
        else:
            _write_table(ws, ooc)
            _autofit(ws)

        ws = wb.create_sheet("RawData")
        _write_table(ws, data)
        ws.freeze_panes = "A2"
        _autofit(ws)

        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        wb.save(out_path)  # images are read at save time, so save inside the tempdir block

    return {
        "rows": len(data),
        "files": int(data["source_file"].nunique()),
        "equipment": len(results),
        "ooc": len(ooc),
        "path": out_path,
    }
