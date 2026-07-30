"""Render a benchmark report JSON into a publishable Markdown summary.

Published tables are generated from machine-readable reports, never
hand-assembled. This module is the human-readable view of the same artifact.
"""

from __future__ import annotations

from typing import Any


def render_markdown(report: dict[str, Any]) -> str:
    """Turn a ``understory-bench`` report dict into Markdown."""
    lines: list[str] = [
        f"# Benchmark report: {report.get('benchmark', '?')}",
        "",
        f"- Detector: `{report.get('detector')} {report.get('detector_version')}`",
        f"- Detector config: `{report.get('detector_config', {})}`",
        f"- Labels: `{report.get('labels_version')}`",
        f"- Methodology: `{report.get('methodology_version')}`",
        "",
        "## Event-level metrics",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Confirmed events | {report.get('n_events')} |",
        f"| Detections | {report.get('n_detections')} |",
        f"| True positives | {report.get('true_positives')} |",
        f"| False positives | {report.get('false_positives')} |",
        f"| False negatives | {report.get('false_negatives')} |",
        f"| Precision | {_fmt(report.get('event_precision'))} |",
        f"| Recall | {_fmt(report.get('event_recall'))} |",
        f"| F1 | {_fmt(report.get('f1'))} |",
        f"| Median detection latency (days) | {report.get('median_detection_latency_days')} |",
        f"| Median lead over optical (days) | {report.get('median_lead_over_optical_days')} |",
        f"| Events with optical record | {report.get('n_events_with_optical_record')} |",
        f"| Mean match IoU | {_fmt(report.get('mean_match_iou'))} |",
        "",
    ]

    curve = report.get("recall_by_area_ha") or {}
    if curve:
        lines += [
            "## Recall by event area (ha)",
            "",
            "| Bin (ha) | Recall |",
            "|---|---|",
        ]
        for bin_name, value in curve.items():
            lines.append(f"| {bin_name} | {_fmt(value)} |")
        lines.append("")

    calibration = report.get("calibration") or {}
    bins = calibration.get("bins") or {}
    if bins:
        lines += [
            "## Confidence calibration",
            "",
            f"Expected calibration error: {calibration.get('expected_calibration_error')}",
            "",
            "| Score bin | Mean score | Confirm rate | n |",
            "|---|---|---|---|",
        ]
        for name, row in bins.items():
            lines.append(
                f"| {name} | {_fmt(row.get('mean_score'))} | "
                f"{_fmt(row.get('confirm_rate'))} | {row.get('n')} |"
            )
        lines.append("")

    verdict = report.get("kill_criteria")
    if verdict:
        lines += [
            "## Kill criteria",
            "",
            f"Synthetic scaffolding: `{verdict.get('synthetic', False)}`",
            "",
            "| Criterion | Threshold | Observed | Verdict |",
            "|---|---|---|---|",
        ]
        for c in verdict.get("criteria", []):
            lines.append(
                f"| {c.get('name')} | {c.get('threshold')} | "
                f"{c.get('observed')} | **{c.get('status')}** |"
            )
        lines.append("")

    lines += [
        "---",
        "",
        "PROVISIONAL NISAR results are exploratory until re-validated on the fully validated "
        "(`NISAR_L2_GUNW_V1`) reprocessing stream.",
        "",
    ]
    return "\n".join(lines)


def _fmt(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)
