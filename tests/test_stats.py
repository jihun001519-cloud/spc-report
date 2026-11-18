import pandas as pd
import pytest

from spc_report import config as C
from spc_report.stats import (compute_limits, control_charts, equipment_summary, make_subgroups,
                              wafer_trace)


def _rows(step, date, wafer, base, equip="T1", lot="L1"):
    return [{C.COL_DATE: pd.Timestamp(date), C.COL_LOT: lot, C.COL_WAFER: wafer,
             C.COL_WAFER_UID: f"{lot}-W{wafer:02d}", C.COL_STEP: step, C.COL_EQUIP: equip,
             C.COL_SITE: i + 1, C.COL_PARAM: "thk", C.COL_UNIT: "nm", C.COL_VALUE: float(base + i)}
            for i in range(5)]


def _toy_data():
    """Two wafers on one tool, 5 sites each, values chosen for hand calculation.

    wafer 1: 10,11,12,13,14 -> xbar=12, R=4
    wafer 2: 20,21,22,23,24 -> xbar=22, R=4
    X-double-bar = 17, R-bar = 4
    """
    return pd.DataFrame(_rows("S1", "2026-11-01", 1, 10) + _rows("S1", "2026-11-01", 2, 20))


def test_subgroups():
    sub = make_subgroups(_toy_data())
    assert sub["xbar"].tolist() == [12.0, 22.0]
    assert sub["range"].tolist() == [4.0, 4.0]


def test_limits_match_hand_calculation():
    lim = compute_limits(make_subgroups(_toy_data()))
    assert lim.n == 5
    assert lim.xbar_cl == pytest.approx(17.0)
    assert lim.xbar_ucl == pytest.approx(17 + 0.577 * 4)   # 19.308
    assert lim.xbar_lcl == pytest.approx(17 - 0.577 * 4)   # 14.692
    assert lim.r_cl == pytest.approx(4.0)
    assert lim.r_ucl == pytest.approx(2.114 * 4)           # 8.456
    assert lim.r_lcl == pytest.approx(0.0)


def test_ooc_flags():
    (res,) = control_charts(_toy_data())
    # both wafer means (12, 22) lie outside 14.69..19.31
    assert res.subgroups["xbar_ooc"].tolist() == [True, True]
    assert not res.subgroups["r_ooc"].any()


def test_summary_stats():
    s = equipment_summary(_toy_data()).set_index(C.COL_EQUIP)
    assert s.loc["T1", "N"] == 10
    assert s.loc["T1", "Mean"] == pytest.approx(17.0)
    assert s.loc["T1", "Min"] == 10 and s.loc["T1", "Max"] == 24


def _two_day_data():
    """Day 1 (Phase I): wafers 10..14 and 20..24.  Day 2 (Phase II): 100..104."""
    return pd.concat([_toy_data(), pd.DataFrame(_rows("S1", "2026-11-02", 3, 100))],
                     ignore_index=True)


def test_phase1_limits_ignore_phase2_data():
    (res,) = control_charts(_two_day_data(), phase1_days=1)
    s = res.subgroups
    assert s["phase"].tolist() == ["I", "I", "II"]
    assert res.limits.xbar_cl == pytest.approx(17.0)
    assert res.limits.xbar_ucl == pytest.approx(17 + 0.577 * 4)
    assert s.loc[s["phase"] == "II", "xbar_ooc"].all()


def test_phase1_days_zero_uses_all_data():
    (res,) = control_charts(_two_day_data(), phase1_days=0)
    assert (res.subgroups["phase"] == "I").all()
    assert res.limits.xbar_cl == pytest.approx((12 + 22 + 102) / 3)


def test_phase1_window_is_per_step():
    """S2 starts 3 days later than S1; its Phase I must start at its own first date."""
    df = pd.DataFrame(_rows("S1", "2026-11-01", 1, 10) + _rows("S1", "2026-11-02", 2, 10)
                      + _rows("S2", "2026-11-04", 1, 50) + _rows("S2", "2026-11-05", 2, 50))
    res = {r.step: r for r in control_charts(df, phase1_days=1, step_order=["S1", "S2"])}
    assert res["S2"].subgroups["phase"].tolist() == ["I", "II"]


def test_charts_split_by_step_and_tool_in_flow_order():
    df = pd.DataFrame(_rows("B", "2026-11-01", 1, 10, equip="X") + _rows("A", "2026-11-01", 1, 10)
                      + _rows("A", "2026-11-01", 2, 10, equip="T2"))
    res = control_charts(df, phase1_days=0, step_order=["B", "A"])
    assert [(r.step, r.equipment) for r in res] == [("B", "X"), ("A", "T1"), ("A", "T2")]


def test_wafer_trace_links_steps():
    df = pd.DataFrame(_rows("S1", "2026-11-01", 1, 10) + _rows("S2", "2026-11-02", 1, 50, equip="E9"))
    t = wafer_trace(df, ["S1", "S2"])
    assert len(t) == 1
    row = t.iloc[0]
    assert row[C.COL_WAFER_UID] == "L1-W01"
    assert row["S1_thk"] == pytest.approx(12.0) and row["S2_thk"] == pytest.approx(52.0)
    assert row["S2_equipment"] == "E9"
