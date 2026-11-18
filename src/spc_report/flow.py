"""Load and validate the process flow definition (TOML)."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from datetime import date
from importlib import resources
from pathlib import Path

from . import config as C


@dataclass(frozen=True)
class Equipment:
    id: str
    offset: float
    sigma: float


@dataclass(frozen=True)
class Step:
    id: str
    name: str
    parameter: str
    unit: str
    target: float
    spec: float
    sites: int
    sigma_lot: float
    sigma_wafer: float
    equipment: tuple[Equipment, ...]

    @property
    def usl(self) -> float:
        return self.target + self.spec

    @property
    def lsl(self) -> float:
        return self.target - self.spec


@dataclass(frozen=True)
class Propagation:
    src: str
    dst: str
    coef: float
    note: str = ""


@dataclass(frozen=True)
class Anomaly:
    type: str               # "shift" | "spike"
    step: str               # step id or "*"
    equipment: str | None = None
    from_day: int = 0
    amount: float = 0.0     # shift size (unit of the step)
    prob: float = 0.0       # spike probability per wafer
    size: float = 0.0       # spike size in multiples of tool sigma


@dataclass(frozen=True)
class Flow:
    steps: tuple[Step, ...]
    propagation: tuple[Propagation, ...]
    anomalies: tuple[Anomaly, ...]
    lots_per_day: int
    wafers_per_lot: int
    start_date: date

    @property
    def step_ids(self) -> list[str]:
        return [s.id for s in self.steps]

    def step(self, step_id: str) -> Step:
        for s in self.steps:
            if s.id == step_id:
                return s
        raise KeyError(step_id)


DEFAULT_FLOW_FILE = "process_flow.toml"


def load_flow(path: Path | str | None = None) -> Flow:
    """Read a flow TOML; None -> the default flow bundled with the package."""
    if path is None:
        raw = resources.files("spc_report").joinpath(DEFAULT_FLOW_FILE).read_text(encoding="utf-8")
    else:
        raw = Path(path).read_text(encoding="utf-8")
    return parse_flow(tomllib.loads(raw))


def parse_flow(d: dict) -> Flow:
    gen = d.get("generation", {})
    steps = tuple(
        Step(
            id=s["id"],
            name=s.get("name", s["id"]),
            parameter=s["parameter"],
            unit=s["unit"],
            target=float(s["target"]),
            spec=float(s["spec"]),
            sites=int(s["sites"]),
            sigma_lot=float(s.get("sigma_lot", 0.0)),
            sigma_wafer=float(s.get("sigma_wafer", 0.0)),
            equipment=tuple(
                Equipment(id=k, offset=float(v.get("offset", 0.0)), sigma=float(v["sigma"]))
                for k, v in s["equipment"].items()
            ),
        )
        for s in d["steps"]
    )
    props = tuple(
        Propagation(src=p["from"], dst=p["to"], coef=float(p["coef"]), note=p.get("note", ""))
        for p in d.get("propagation", [])
    )
    anomalies = tuple(
        Anomaly(
            type=a["type"],
            step=a.get("step", "*"),
            equipment=a.get("equipment"),
            from_day=int(a.get("from_day", 0)),
            amount=float(a.get("amount", 0.0)),
            prob=float(a.get("prob", 0.0)),
            size=float(a.get("size", 0.0)),
        )
        for a in d.get("anomalies", [])
    )
    flow = Flow(
        steps=steps,
        propagation=props,
        anomalies=anomalies,
        lots_per_day=int(gen.get("lots_per_day", 4)),
        wafers_per_lot=int(gen.get("wafers_per_lot", 8)),
        start_date=date.fromisoformat(str(gen.get("start_date", "2026-11-01"))),
    )
    validate(flow)
    return flow


def validate(flow: Flow) -> None:
    ids = flow.step_ids
    if not ids:
        raise ValueError("flow has no steps")
    if len(set(ids)) != len(ids):
        raise ValueError(f"duplicate step ids: {ids}")
    for s in flow.steps:
        if s.sites not in C.SPC_CONSTANTS:
            raise ValueError(f"{s.id}: sites={s.sites} not supported (use {sorted(C.SPC_CONSTANTS)})")
        if not s.equipment:
            raise ValueError(f"{s.id}: no equipment")
    for p in flow.propagation:
        for sid in (p.src, p.dst):
            if sid not in ids:
                raise ValueError(f"propagation refers to unknown step {sid!r}")
        if ids.index(p.src) >= ids.index(p.dst):
            raise ValueError(f"propagation {p.src}->{p.dst}: source must come before target")
    for a in flow.anomalies:
        if a.type not in ("shift", "spike"):
            raise ValueError(f"unknown anomaly type {a.type!r}")
        if a.step != "*" and a.step not in ids:
            raise ValueError(f"anomaly refers to unknown step {a.step!r}")
        if a.equipment and a.step != "*" and a.equipment not in {e.id for e in flow.step(a.step).equipment}:
            raise ValueError(f"anomaly refers to unknown equipment {a.equipment!r} in {a.step}")
