"""Round-tripping a report must reproduce its metrics exactly.

Per-item timings are the expensive part of a load run. Every derived metric is a
pure function of them, so a stored run can be re-judged when a threshold moves
or when a derived metric turns out to have been wrong — without paying for the
run again.
"""

from __future__ import annotations

import json

import pytest
from understory_perf import slo
from understory_perf.cli import rescore, run_scenario
from understory_perf.runner import RunResult


@pytest.fixture
def report(tmp_path):
    from understory_perf.cli import ScenarioConfig

    config = ScenarioConfig(
        name="tiny",
        shape="cycle-burst",
        n_aoi=1,
        stack_depth=6,
        posting="coarse",
        aoi_side_km=6.0,
        workers=2,
        compression=1e-4,
    )
    path = tmp_path / "tiny.json"
    path.write_text(json.dumps(run_scenario(config), indent=2))
    return path


def test_round_trip_preserves_every_derived_metric(report):
    original = json.loads(report.read_text())
    rescored = rescore(report)
    for key, value in original["run"].items():
        assert rescored["run"][key] == value, f"{key} changed on rescore"
    assert rescored["capacity"] == original["capacity"]


def test_round_trip_preserves_the_verdict(report):
    original = json.loads(report.read_text())
    assert rescore(report)["slo"]["objectives"] == original["slo"]["objectives"]


def test_rescore_records_its_provenance(report):
    rescored = rescore(report)
    assert rescored["rescored_from"] == str(report)
    assert "rescored_at" in rescored
    # The original run's identity survives, so a rescored report is still
    # traceable to the machine and revision that produced the timings.
    assert rescored["generated_at"] == json.loads(report.read_text())["generated_at"]


def test_rescore_applies_current_thresholds(report, monkeypatch):
    """The point of rescoring: a moved threshold re-judges an old run."""
    monkeypatch.setattr(slo, "MAX_UTILIZATION", -1.0)
    verdict = slo.evaluate(RunResult.from_report(json.loads(report.read_text())))
    assert next(o for o in verdict.objectives if o.name == "cycle-utilization").status == "FAIL"
