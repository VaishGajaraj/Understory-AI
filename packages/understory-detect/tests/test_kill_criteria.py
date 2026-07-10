from understory_detect.kill_criteria import evaluate, format_table
from understory_detect.scoring import BenchmarkReport, MatchingTolerances


def report_with(**overrides) -> BenchmarkReport:
    defaults = dict(
        benchmark="test",
        detector="v0-filters",
        detector_version="0.1.0",
        labels_version="0.1.0",
        methodology_version="0.1.0",
        tolerances=MatchingTolerances(),
        n_events=10,
        n_detections=10,
        true_positives=8,
        false_positives=2,
        false_negatives=2,
        event_precision=0.8,
        event_recall=0.8,
        f1=0.8,
    )
    defaults.update(overrides)
    return BenchmarkReport.model_validate(defaults)


def by_name(verdict):
    return {c.name: c for c in verdict.criteria}


def test_all_pass_on_strong_real_benchmark():
    report = report_with(
        median_lead_over_optical_days=25.0,
        n_events_with_optical_record=6,
        recall_by_area_ha={"1-2": 0.7, "2-5": 0.9},
    )
    verdict = evaluate(report, synthetic=False)
    assert by_name(verdict)["precision"].status == "PASS"
    assert by_name(verdict)["min-detectable-size"].status == "PASS"
    assert by_name(verdict)["lead-over-optical"].status == "PASS"
    assert verdict.alive


def test_low_precision_is_a_kill():
    report = report_with(event_precision=0.5)
    verdict = evaluate(report, synthetic=False)
    assert by_name(verdict)["precision"].status == "FAIL"
    assert not verdict.alive


def test_missing_evidence_is_insufficient_not_fail():
    report = report_with()  # no optical records, no small-size bins
    verdict = evaluate(report, synthetic=False)
    assert by_name(verdict)["min-detectable-size"].status == "INSUFFICIENT_DATA"
    assert by_name(verdict)["lead-over-optical"].status == "INSUFFICIENT_DATA"
    assert verdict.alive  # unknown is not dead


def test_small_events_never_found_is_a_kill():
    report = report_with(recall_by_area_ha={"0-1": 0.0, "1-2": 0.0, "20+": 1.0})
    verdict = evaluate(report, synthetic=False)
    assert by_name(verdict)["min-detectable-size"].status == "FAIL"


def test_synthetic_passes_are_marked_as_scaffolding():
    report = report_with(median_lead_over_optical_days=25.0, n_events_with_optical_record=1)
    verdict = evaluate(report, synthetic=True)
    lead = by_name(verdict)["lead-over-optical"]
    assert lead.status == "PASS"
    assert "not a claim" in lead.note
    assert "synthetic" in format_table(verdict) or verdict.synthetic
