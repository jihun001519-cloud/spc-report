"""Command-line entry points: `spc-generate` and `spc-report`."""

from __future__ import annotations

import argparse
from pathlib import Path

from . import config as C
from .generate import generate
from .report import build_report


def generate_main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Generate synthetic thickness data (one Excel per day)")
    p.add_argument("--out", type=Path, default=C.DEFAULT_DATA_DIR, help="output folder")
    p.add_argument("--days", type=int, default=10, help="number of days = number of files")
    p.add_argument("--wafers", type=int, default=8, help="wafers per lot")
    p.add_argument("--seed", type=int, default=42)
    a = p.parse_args(argv)

    paths = generate(a.out, n_days=a.days, seed=a.seed, wafers_per_lot=a.wafers)
    print(f"Created {len(paths)} files in {a.out}/")
    for path in paths:
        print(f"  {path.name}")


def report_main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Build an SPC Excel report from a folder of Excel files")
    p.add_argument("--in", dest="inp", type=Path, default=C.DEFAULT_DATA_DIR, help="input folder")
    p.add_argument("--out", type=Path, default=C.DEFAULT_REPORT_PATH, help="report .xlsx path")
    a = p.parse_args(argv)

    info = build_report(a.inp, a.out)
    print(f"Merged {info['files']} files / {info['rows']} rows, {info['equipment']} tools")
    print(f"Out-of-control subgroups: {info['ooc']}")
    print(f"Report saved: {info['path']}")
