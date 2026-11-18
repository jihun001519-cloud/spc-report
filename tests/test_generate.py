import pandas as pd

from spc_report import config as C
from spc_report.generate import generate, generate_dataframe
from spc_report.loader import load_folder


def test_dataframe_shape_and_columns():
    df = generate_dataframe(n_days=3, wafers_per_lot=4, seed=1)
    n_equip = len(C.EQUIPMENT_PROFILES)
    assert list(df.columns) == C.REQUIRED_COLUMNS
    assert len(df) == 3 * n_equip * 4 * C.SITES_PER_WAFER


def test_seed_is_reproducible():
    a = generate_dataframe(n_days=2, seed=7)
    b = generate_dataframe(n_days=2, seed=7)
    pd.testing.assert_frame_equal(a, b)


def test_mean_shift_is_injected():
    df = generate_dataframe(n_days=10, seed=3, spike_prob=0.0, shift_equipment="CVD-01",
                            shift_from_day=5, shift_nm=20.0)
    cvd1 = df[df[C.COL_EQUIP] == "CVD-01"]
    cutoff = cvd1[C.COL_DATE].min() + pd.Timedelta(days=5)
    before = cvd1[cvd1[C.COL_DATE] < cutoff][C.COL_THICK].mean()
    after = cvd1[cvd1[C.COL_DATE] >= cutoff][C.COL_THICK].mean()
    assert after - before > 10


def test_files_written_and_reloaded(tmp_path):
    paths = generate(tmp_path, n_days=4, seed=0)
    assert len(paths) == 4
    merged = load_folder(tmp_path)
    assert merged["source_file"].nunique() == 4
    assert merged[C.COL_THICK].notna().all()
