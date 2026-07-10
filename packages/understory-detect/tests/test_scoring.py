from datetime import date, datetime

from understory_detect.interface import Detection
from understory_detect.scoring import MatchingTolerances, score
from understory_labels.events import ConfirmationStatus, DateWindow, DisturbanceEvent


def event(
    id: str, lon: float, lat: float, status: ConfirmationStatus = "confirmed"
) -> DisturbanceEvent:
    return DisturbanceEvent(
        id=id,
        geometry={"type": "Point", "coordinates": [lon, lat]},
        date_window=DateWindow(start=date(2026, 2, 1), end=date(2026, 2, 13)),
        event_class="access-road",
        status=status,
        biome="amazon-moist-forest",
        evidence_source="test-fixture",
    )


def detection(id: str, lon: float, lat: float, score_: float = 0.9) -> Detection:
    return Detection(
        id=id,
        geometry={"type": "Point", "coordinates": [lon, lat]},
        first_seen=datetime(2026, 2, 7),
        last_seen=datetime(2026, 2, 19),
        score=score_,
        persistence_passes=2,
    )


def make_report(detections, events):
    return score(
        detections,
        events,
        MatchingTolerances(),
        benchmark="test",
        detector="v0-filters",
        detector_version="0.1.0",
        labels_version="0.1.0",
        methodology_version="0.1.0",
    )


def test_perfect_match():
    report = make_report([detection("d1", -55.0, -7.0)], [event("e1", -55.0, -7.0)])
    assert report.true_positives == 1
    assert report.event_precision == 1.0
    assert report.event_recall == 1.0


def test_distant_detection_is_false_positive():
    # ~1 degree away — far outside the 500 m tolerance
    report = make_report([detection("d1", -56.0, -7.0)], [event("e1", -55.0, -7.0)])
    assert report.true_positives == 0
    assert report.false_positives == 1
    assert report.false_negatives == 1


def test_rejected_labels_do_not_count_as_events():
    report = make_report(
        [detection("d1", -55.0, -7.0)],
        [event("e1", -55.0, -7.0, status="rejected")],
    )
    assert report.n_events == 0
    assert report.false_positives == 1


def test_lead_over_optical_and_size_curve():
    ev = DisturbanceEvent(
        id="e1",
        geometry={"type": "Point", "coordinates": [-55.0, -7.0]},
        date_window=DateWindow(start=date(2026, 2, 1), end=date(2026, 2, 13)),
        event_class="access-road",
        status="confirmed",
        biome="amazon-moist-forest",
        evidence_source="test-fixture",
        area_ha=1.5,
        optical_alert_date=date(2026, 3, 1),
    )
    missed = DisturbanceEvent(
        id="e2",
        geometry={"type": "Point", "coordinates": [-56.0, -8.0]},
        date_window=DateWindow(start=date(2026, 2, 1), end=date(2026, 2, 13)),
        event_class="clearing",
        status="confirmed",
        biome="amazon-moist-forest",
        evidence_source="test-fixture",
        area_ha=30.0,
    )
    report = make_report([detection("d1", -55.0, -7.0)], [ev, missed])
    # detected 2026-02-07; optical alert 2026-03-01 -> 22 days lead
    assert report.median_lead_over_optical_days == 22.0
    assert report.n_events_with_optical_record == 1
    # size curve: the 1.5 ha event was found, the 30 ha event was missed
    assert report.recall_by_area_ha == {"1-2": 1.0, "20+": 0.0}


def test_calibration_measures_overconfidence():
    # Two high-score detections: one confirms, one is a false alarm.
    # Confirm rate in the 0.8-1.0 bin should be 0.5 against mean score 0.9.
    report = make_report(
        [detection("d1", -55.0, -7.0, 0.9), detection("d2", -50.0, -3.0, 0.9)],
        [event("e1", -55.0, -7.0)],
    )
    bin_ = report.calibration.bins["0.8-1.0"]
    assert bin_.n == 2
    assert bin_.confirm_rate == 0.5
    ece = report.calibration.expected_calibration_error
    assert ece is not None and abs(ece - 0.4) < 0.01  # |0.9 - 0.5|


def test_one_to_one_matching():
    # Two detections near one event: only one true positive.
    report = make_report(
        [detection("d1", -55.0, -7.0), detection("d2", -55.001, -7.0)],
        [event("e1", -55.0, -7.0)],
    )
    assert report.true_positives == 1
    assert report.false_positives == 1
