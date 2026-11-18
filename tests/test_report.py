from openpyxl import load_workbook

from spc_report.flow import load_flow
from spc_report.generate import generate
from spc_report.report import build_report


def test_end_to_end(tmp_path):
    flow = load_flow()
    data_dir = tmp_path / "data"
    out = tmp_path / "out" / "report.xlsx"
    generate(data_dir, n_days=10, seed=42)

    info = build_report(data_dir, out)

    assert out.exists()
    assert info["steps"] == len(flow.steps)
    assert info["charts"] == sum(len(s.equipment) for s in flow.steps)
    assert info["wafers"] == 10 * flow.lots_per_day * flow.wafers_per_lot
    assert info["ooc"] > 0, "injected anomalies should produce OOC points"

    wb = load_workbook(out)
    expected = ["Summary", "Flow", *flow.step_ids, "WaferTrace", "OOC_List", "RawData"]
    assert wb.sheetnames == expected
    for s in flow.steps:
        assert len(wb[s.id]._images) == len(s.equipment)
