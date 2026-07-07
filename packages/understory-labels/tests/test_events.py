from pathlib import Path

import pytest
from understory_labels.events import load_collection
from understory_labels.validate import validate_file

DATA_DIR = Path(__file__).parents[1] / "data" / "events"


def test_all_committed_label_files_are_valid():
    files = sorted(DATA_DIR.glob("*.geojson"))
    assert files, "no label files found — the toy fixtures should exist"
    for path in files:
        assert validate_file(path) == []


def test_load_toy_fixtures():
    events = load_collection(DATA_DIR / "toy-fixtures.geojson")
    assert {e.id for e in events} == {"toy-road-001", "toy-rain-001"}
    statuses = {e.id: e.status for e in events}
    assert statuses["toy-road-001"] == "confirmed"
    assert statuses["toy-rain-001"] == "rejected"


def test_invalid_date_window_rejected():
    from datetime import date

    from understory_labels.events import DateWindow

    with pytest.raises(ValueError):
        DateWindow(start=date(2026, 3, 1), end=date(2026, 2, 1))
