import copy
import tomllib
from importlib import resources

import numpy as np
import pandas as pd

from spc_report import config as C
from spc_report.flow import load_flow, parse_flow
from spc_report.generate import generate, generate_dataframe
from spc_report.loader import load_folder


def _wafer_means(df):
    return df.groupby([C.COL_WAFER_UID, C.COL_STEP])[C.COL_VALUE].mean().unstack()


def _quiet_flow():
    """Default flow tuned so the slope estimate is precise (standard error ~0.01).

    slope SE ~ sigma(dst own noise) / (sigma(src) * sqrt(n)), so sources vary a lot
    (wafer sigma 5), destinations barely (0.5), site noise ~0, no lot clustering, no anomalies.
    """
    raw = tomllib.loads(resources.files("spc_report").joinpath("process_flow.toml")
                        .read_text(encoding="utf-8"))
    raw = copy.deepcopy(raw)
    downstream = {p["to"] for p in raw["propagation"]}
    for s in raw["steps"]:
        s["sigma_lot"] = 0.0
        s["sigma_wafer"] = 0.5 if s["id"] in downstream else 5.0
        for e in s["equipment"].values():
            e["sigma"], e["offset"] = 0.01, 0.0
    raw["anomalies"] = []
    return parse_flow(raw)


def test_shape_and_columns():
    flow = load_flow()
    df = generate_dataframe(flow, n_days=2, seed=1)
    assert list(df.columns) == C.REQUIRED_COLUMNS
    n_wafers = 2 * flow.lots_per_day * flow.wafers_per_lot
    assert len(df) == n_wafers * sum(s.sites for s in flow.steps)


def test_every_wafer_visits_every_step_in_order():
    flow = load_flow()
    df = generate_dataframe(flow, n_days=3, seed=1)
    w = df.groupby([C.COL_WAFER_UID, C.COL_STEP])[C.COL_DATE].first().unstack()
    assert w.notna().all().all()
    for k, step in enumerate(flow.step_ids):
        assert ((w[step] - w[flow.step_ids[0]]).dt.days == k).all()


def test_seed_is_reproducible():
    pd.testing.assert_frame_equal(generate_dataframe(n_days=2, seed=7),
                                  generate_dataframe(n_days=2, seed=7))


def test_propagation_coefficients_recovered():
    w = _wafer_means(generate_dataframe(_quiet_flow(), n_days=10, seed=3))
    slope = lambda a, b: np.polyfit(w[a], w[b], 1)[0]  # noqa: E731
    assert abs(slope("DEP", "CMP") - 0.7) < 0.05
    assert abs(slope("PH", "ET") - 0.4) < 0.05
    assert abs(slope("OX", "CMP")) < 0.15          # no injected effect


def test_mean_shift_is_injected():
    df = generate_dataframe(n_days=10, seed=3)
    dep = df[(df[C.COL_STEP] == "DEP") & (df[C.COL_EQUIP] == "CVD-02")]
    day = (dep[C.COL_DATE] - pd.Timestamp(load_flow().start_date)).dt.days
    assert dep[day >= 10][C.COL_VALUE].mean() - dep[day < 10][C.COL_VALUE].mean() > 8


def test_files_written_per_step_and_reloaded(tmp_path):
    paths = generate(tmp_path, n_days=2, seed=0)
    flow = load_flow()
    # each step spans 2 days -> 2 files per step, in data/<STEP>/<STEP>_<date>.xlsx
    assert len(paths) == 2 * len(flow.steps)
    assert {p.parent.name for p in paths} == set(flow.step_ids)
    assert all(p.name.startswith(p.parent.name + "_") for p in paths)
    merged = load_folder(tmp_path)
    assert merged["source_file"].nunique() == len(paths)
    assert merged[C.COL_VALUE].notna().all()
