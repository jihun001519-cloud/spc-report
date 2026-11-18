"""Command-line entry points: `spc-generate` and `spc-report`."""

from __future__ import annotations

import argparse
from pathlib import Path

from . import config as C
from .flow import load_flow
from .generate import generate
from .report import build_report

FLOW_HELP = "process flow TOML (default: bundled STI flow)"


def generate_main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Generate synthetic multi-step measurement data "
                                            "(data/<STEP>/<STEP>_<date>.xlsx)")
    p.add_argument("--out", type=Path, default=C.DEFAULT_DATA_DIR, help="output folder")
    p.add_argument("--days", type=int, default=10, help="number of days lots are started")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--flow", type=Path, default=None, help=FLOW_HELP)
    a = p.parse_args(argv)

    flow = load_flow(a.flow)
    paths = generate(a.out, n_days=a.days, seed=a.seed, flow=flow)
    print(f"Created {len(paths)} files in {a.out}/ ({len(flow.steps)} steps: "
          f"{' -> '.join(flow.step_ids)})")


def report_main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Build an SPC Excel report from a folder of Excel files")
    p.add_argument("--in", dest="inp", type=Path, default=C.DEFAULT_DATA_DIR, help="input folder")
    p.add_argument("--out", type=Path, default=C.DEFAULT_REPORT_PATH, help="report .xlsx path")
    p.add_argument("--phase1-days", type=int, default=C.DEFAULT_PHASE1_DAYS,
                   help="first N days of each step set the control limits (0 = use all data)")
    p.add_argument("--flow", type=Path, default=None, help=FLOW_HELP)
    a = p.parse_args(argv)

    info = build_report(a.inp, a.out, phase1_days=a.phase1_days, flow=load_flow(a.flow))
    print(f"Merged {info['files']} files / {info['rows']} rows / {info['wafers']} wafers, "
          f"{info['steps']} steps, {info['charts']} charts")
    print(f"Out-of-control subgroups: {info['ooc']}")
    print(f"Report saved: {info['path']}")
