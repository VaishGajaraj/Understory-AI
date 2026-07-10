"""Kill criteria as code — the go/no-go gate stated before building.

The project lives or dies on three numbers (METHODOLOGY.md sec 5), so they are
defined here, evaluated on every benchmark report, and echoed into the report
itself. If the verdict were assembled by hand it would read as theatre.

A criterion can be PASS, FAIL, or INSUFFICIENT_DATA — and the honest state
matters: a toy benchmark cannot prove the 2 ha criterion, and a label set with
no optical record cannot prove the lead criterion. Only real granules against
external ground truth can turn everything green; synthetic results are
scaffolding, never claims.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from understory_detect.scoring import BenchmarkReport

# The three thresholds, verbatim from the methodology document.
PRECISION_MIN = 0.70
MIN_DETECTABLE_HA = 2.0
LEAD_OVER_OPTICAL_MIN_DAYS = 21.0

Status = Literal["PASS", "FAIL", "INSUFFICIENT_DATA"]


class Criterion(BaseModel):
    name: str
    threshold: str
    observed: str
    status: Status
    note: str = ""


class KillCriteriaVerdict(BaseModel):
    criteria: list[Criterion]
    synthetic: bool = False

    @property
    def alive(self) -> bool:
        """The thesis survives while nothing has FAILED."""
        return all(c.status != "FAIL" for c in self.criteria)


def evaluate(report: BenchmarkReport, *, synthetic: bool) -> KillCriteriaVerdict:
    criteria = [
        _precision(report),
        _min_size(report),
        _lead(report),
    ]
    if synthetic:
        for criterion in criteria:
            if criterion.status == "PASS":
                criterion.note = (
                    criterion.note + " synthetic data — scaffolding, not a claim"
                ).strip()
    return KillCriteriaVerdict(criteria=criteria, synthetic=synthetic)


def _precision(report: BenchmarkReport) -> Criterion:
    if report.n_events == 0:
        return Criterion(
            name="precision",
            threshold=f">= {PRECISION_MIN:.0%}",
            observed="no confirmed events in label set",
            status="INSUFFICIENT_DATA",
        )
    status: Status = "PASS" if report.event_precision >= PRECISION_MIN else "FAIL"
    return Criterion(
        name="precision",
        threshold=f">= {PRECISION_MIN:.0%}",
        observed=f"{report.event_precision:.0%} ({report.true_positives}/{report.n_detections})",
        status=status,
        note=f"recall {report.event_recall:.0%}",
    )


def _min_size(report: BenchmarkReport) -> Criterion:
    # Detectability at or below the threshold: any populated bin whose upper
    # bound is <= MIN_DETECTABLE_HA must show nonzero recall.
    small_bins = {
        name: value
        for name, value in report.recall_by_area_ha.items()
        if _bin_upper(name) <= MIN_DETECTABLE_HA
    }
    if not small_bins:
        return Criterion(
            name="min-detectable-size",
            threshold=f"events <= {MIN_DETECTABLE_HA:g} ha detectable",
            observed="no labeled events at or below the threshold size",
            status="INSUFFICIENT_DATA",
            note="needs controlled-disturbance ground truth (eastern-woodland benchmark)",
        )
    detected = any(value > 0 for value in small_bins.values())
    return Criterion(
        name="min-detectable-size",
        threshold=f"events <= {MIN_DETECTABLE_HA:g} ha detectable",
        observed=", ".join(f"{k} ha: {v:.0%}" for k, v in sorted(small_bins.items())),
        status="PASS" if detected else "FAIL",
    )


def _lead(report: BenchmarkReport) -> Criterion:
    if report.median_lead_over_optical_days is None:
        return Criterion(
            name="lead-over-optical",
            threshold=f">= {LEAD_OVER_OPTICAL_MIN_DAYS:g} days median",
            observed=(
                f"{report.n_events_with_optical_record} events carry an optical record, "
                "none matched"
                if report.n_events_with_optical_record
                else "no optical alert records in label set"
            ),
            status="INSUFFICIENT_DATA",
        )
    status: Status = (
        "PASS" if report.median_lead_over_optical_days >= LEAD_OVER_OPTICAL_MIN_DAYS else "FAIL"
    )
    return Criterion(
        name="lead-over-optical",
        threshold=f">= {LEAD_OVER_OPTICAL_MIN_DAYS:g} days median",
        observed=f"{report.median_lead_over_optical_days:g} days "
        f"(n={report.n_events_with_optical_record})",
        status=status,
    )


def _bin_upper(bin_name: str) -> float:
    if bin_name.endswith("+"):
        return float("inf")
    return float(bin_name.split("-")[1])


def format_table(verdict: KillCriteriaVerdict) -> str:
    lines = ["kill criteria:"]
    for criterion in verdict.criteria:
        note = f"  ({criterion.note})" if criterion.note else ""
        lines.append(
            f"  [{criterion.status:^17s}] {criterion.name}: {criterion.observed} "
            f"vs {criterion.threshold}{note}"
        )
    lines.append(f"  verdict: {'thesis alive' if verdict.alive else 'KILL CONDITION MET'}")
    return "\n".join(lines)
