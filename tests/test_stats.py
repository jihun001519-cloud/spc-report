import pandas as pd
import pytest

from spc_report import config as C
from spc_report.stats import compute_limits, control_charts, equipment_summary, make_subgroups


def _toy_data():
    """Two wafers on one tool, 5 sites each, values chosen for hand calculation.

    wafer 1: 10,11,12,13,14 -> xbar=12, R=4
    wafer 2: 20,21,22,23,24 -> xbar=22, R=4
    X-double-bar = 17, R-bar = 4
    """
    rows = []
    for wafer, base in ((1, 10), (2, 20)):
        for site in range(5):
            rows.append({C.COL_DATE: pd.Timestamp("2026-11-01"), C.COL_LOT: "L1", C.COL_WAFER: wafer,
                         C.COL_EQUIP: "T1", C.COL_SITE: site + 1, C.COL_THICK: float(base + site)})
    return pd.DataFrame(rows)


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
    df = _toy_data()
    day2 = df[df[C.COL_WAFER] == 1].copy()
    day2[C.COL_DATE] = pd.Timestamp("2026-11-02")
    day2[C.COL_WAFER] = 3
    day2[C.COL_THICK] = day2[C.COL_THICK] + 90  # 100..104
    return pd.concat([df, day2], ignore_index=True)


def test_phase1_limits_ignore_phase2_data():
    (res,) = control_charts(_two_day_data(), phase1_days=1)
    s = res.subgroups
    assert s["phase"].tolist() == ["I", "I", "II"]
    # limits identical to the day-1-only hand calculation
    assert res.limits.xbar_cl == pytest.approx(17.0)
    assert res.limits.xbar_ucl == pytest.approx(17 + 0.577 * 4)
    assert s.loc[s["phase"] == "II", "xbar_ooc"].all()


def test_phase1_days_zero_uses_all_data():
    (res,) = control_charts(_two_day_data(), phase1_days=0)
    assert (res.subgroups["phase"] == "I").all()
    assert res.limits.xbar_cl == pytest.approx((12 + 22 + 102) / 3)
