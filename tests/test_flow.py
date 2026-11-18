import copy
import tomllib
from importlib import resources

import pytest

from spc_report.flow import load_flow, parse_flow


def _raw():
    text = resources.files("spc_report").joinpath("process_flow.toml").read_text(encoding="utf-8")
    return tomllib.loads(text)


def test_default_flow_loads_in_order():
    flow = load_flow()
    assert flow.step_ids == ["OX", "PH", "ET", "DEP", "CMP"]
    assert {(p.src, p.dst, p.coef) for p in flow.propagation} == {("DEP", "CMP", 0.7),
                                                                   ("PH", "ET", 0.4)}
    dep = flow.step("DEP")
    assert dep.usl == 1030 and dep.lsl == 970


def test_propagation_must_go_downstream():
    raw = copy.deepcopy(_raw())
    raw["propagation"].append({"from": "CMP", "to": "OX", "coef": 0.5})
    with pytest.raises(ValueError, match="source must come before target"):
        parse_flow(raw)


def test_unknown_anomaly_equipment_rejected():
    raw = copy.deepcopy(_raw())
    raw["anomalies"][0]["equipment"] = "CVD-99"
    with pytest.raises(ValueError, match="unknown equipment"):
        parse_flow(raw)


def test_unsupported_subgroup_size_rejected():
    raw = copy.deepcopy(_raw())
    raw["steps"][0]["sites"] = 9
    with pytest.raises(ValueError, match="not supported"):
        parse_flow(raw)
