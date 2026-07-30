from understory_detect.report import render_markdown


def test_render_markdown_includes_core_sections():
    report = {
        "benchmark": "toy",
        "detector": "v0-filters",
        "detector_version": "0.1.0",
        "labels_version": "0.1.0",
        "methodology_version": "0.1.0",
        "n_events": 1,
        "n_detections": 1,
        "true_positives": 1,
        "false_positives": 0,
        "false_negatives": 0,
        "event_precision": 1.0,
        "event_recall": 1.0,
        "f1": 1.0,
        "median_detection_latency_days": 6.0,
        "median_lead_over_optical_days": 22.0,
        "n_events_with_optical_record": 1,
        "mean_match_iou": 0.4,
        "recall_by_area_ha": {"5-20": 1.0},
        "calibration": {
            "expected_calibration_error": 0.1,
            "bins": {
                "0.8-1.0": {"mean_score": 0.9, "confirm_rate": 1.0, "n": 1},
            },
        },
        "kill_criteria": {
            "synthetic": True,
            "criteria": [
                {
                    "name": "precision",
                    "threshold": ">= 70%",
                    "observed": "100%",
                    "status": "PASS",
                }
            ],
        },
    }
    md = render_markdown(report)
    assert "# Benchmark report: toy" in md
    assert "Precision" in md
    assert "Confidence calibration" in md
    assert "Kill criteria" in md
    assert "**PASS**" in md
