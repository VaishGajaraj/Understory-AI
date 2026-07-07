"""The benchmark scoring harness.

Given any detector's output and any labeled event set, produce event-level
precision/recall/F1 (with spatial and temporal matching tolerances stated
explicitly and recorded in the report), detection latency versus event date,
detection lead versus the optical alert record, and minimum-detectable-size
curves. Every run emits a machine-readable report; published tables are
generated from these reports, never hand-assembled.
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from shapely.geometry import shape
from understory_labels.events import DisturbanceEvent

from understory_detect.interface import Detection


class MatchingTolerances(BaseModel):
    """Explicit matching rules — these numbers appear in the methodology doc."""

    max_centroid_distance_m: float = 500.0
    min_spatial_iou: float = 0.0  # v0 matches on distance; IoU reported, not required
    temporal_window_days: int = 36  # +/- 3 repeat cycles around the event window


class BenchmarkReport(BaseModel):
    benchmark: str
    detector: str
    detector_version: str
    labels_version: str
    methodology_version: str
    tolerances: MatchingTolerances
    n_events: int
    n_detections: int
    true_positives: int
    false_positives: int
    false_negatives: int
    event_precision: float = Field(ge=0.0, le=1.0)
    event_recall: float = Field(ge=0.0, le=1.0)
    f1: float = Field(ge=0.0, le=1.0)
    median_detection_latency_days: float | None = None
    median_lead_over_optical_days: float | None = None


def match_detections(
    detections: list[Detection],
    events: list[DisturbanceEvent],
    tolerances: MatchingTolerances,
) -> list[tuple[Detection, DisturbanceEvent]]:
    """Greedy one-to-one matching by centroid distance within the temporal window."""
    matches: list[tuple[Detection, DisturbanceEvent]] = []
    unmatched = list(events)
    for det in sorted(detections, key=lambda d: -d.score):
        det_centroid = shape(det.geometry).centroid
        best: DisturbanceEvent | None = None
        best_dist = float("inf")
        for ev in unmatched:
            if not _temporally_compatible(det, ev, tolerances.temporal_window_days):
                continue
            dist = _distance_m(det_centroid, shape(ev.geometry).centroid)
            if dist <= tolerances.max_centroid_distance_m and dist < best_dist:
                best, best_dist = ev, dist
        if best is not None:
            matches.append((det, best))
            unmatched.remove(best)
    return matches


def score(
    detections: list[Detection],
    events: list[DisturbanceEvent],
    tolerances: MatchingTolerances | None = None,
    *,
    benchmark: str,
    detector: str,
    detector_version: str,
    labels_version: str,
    methodology_version: str,
) -> BenchmarkReport:
    """Event-level scoring. Only 'confirmed' labels count as positives;
    detections matching 'rejected' labels count as false positives."""
    tolerances = tolerances or MatchingTolerances()
    confirmed = [e for e in events if e.status == "confirmed"]
    matches = match_detections(detections, confirmed, tolerances)
    tp = len(matches)
    fp = len(detections) - tp
    fn = len(confirmed) - tp
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    # Latency: first anomalous pair midpoint minus event window start. Negative
    # values are possible when the window is conservative and are reported as-is.
    latencies = sorted((det.first_seen.date() - ev.date_window.start).days for det, ev in matches)
    median_latency = float(latencies[len(latencies) // 2]) if latencies else None
    return BenchmarkReport(
        benchmark=benchmark,
        detector=detector,
        detector_version=detector_version,
        labels_version=labels_version,
        methodology_version=methodology_version,
        tolerances=tolerances,
        n_events=len(confirmed),
        n_detections=len(detections),
        true_positives=tp,
        false_positives=fp,
        false_negatives=fn,
        event_precision=precision,
        event_recall=recall,
        f1=f1,
        median_detection_latency_days=median_latency,
    )


def _temporally_compatible(det: Detection, ev: DisturbanceEvent, window_days: int) -> bool:
    from datetime import timedelta

    pad = timedelta(days=window_days)
    first_seen = det.first_seen.date()
    return ev.date_window.start - pad <= first_seen <= ev.date_window.end + pad


def _distance_m(a, b) -> float:
    """Approximate great-circle distance between two lon/lat points in meters."""
    import math

    lat = math.radians((a.y + b.y) / 2)
    dx = (a.x - b.x) * 111_320 * math.cos(lat)
    dy = (a.y - b.y) * 110_540
    return math.hypot(dx, dy)
