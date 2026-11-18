from openpyxl import load_workbook

from spc_report import config as C
from spc_report.generate import generate
from spc_report.report import build_report


def test_end_to_end(tmp_path):
    data_dir = tmp_path / "data"
    out = tmp_path / "out" / "report.xlsx"
    generate(data_dir, n_days=10, seed=42)

    info = build_report(data_dir, out)

    assert out.exists()
    assert info["files"] == 10
    assert info["ooc"] > 0, "injected anomalies should produce OOC points"

    wb = load_workbook(out)
    expected = {"Summary", "OOC_List", "RawData"} | {f"XbarR_{e}" for e in C.EQUIPMENT_PROFILES}
    assert expected <= set(wb.sheetnames)
    for e in C.EQUIPMENT_PROFILES:
        assert len(wb[f"XbarR_{e}"]._images) == 1
