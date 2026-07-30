import json
from datetime import datetime
from pathlib import Path

from understory_core.discovery import GunwPair
from understory_detect import product_cli


def _pair() -> GunwPair:
    return GunwPair(
        granule_id="NISAR-test-pair",
        track=42,
        frame=7,
        flight_direction="DESCENDING",
        reference_start=datetime.fromisoformat("2026-06-17T12:00:00"),
        secondary_start=datetime.fromisoformat("2026-06-29T12:00:00"),
        url="https://example.test/granule.h5",
        s3_url="s3://example/granule.h5",
        calibration_tier="provisional",
    )


def test_doctor_json_does_not_expose_credentials(tmp_path: Path, capsys):
    credentials = tmp_path / "netrc"
    credentials.write_text(
        "machine urs.earthdata.nasa.gov login private-user password very-secret\n"
    )
    result = product_cli.main(
        [
            "doctor",
            "--json",
            "--require-earthdata",
            "--earthdata-netrc",
            str(credentials),
            "--data-dir",
            str(tmp_path),
        ]
    )
    output = capsys.readouterr().out
    payload = json.loads(output)

    assert result == 0
    assert payload["ready"] is True
    assert "private-user" not in output
    assert "very-secret" not in output


def test_doctor_requires_earthdata_when_requested(tmp_path: Path):
    result = product_cli.doctor(
        earthdata_path=tmp_path / "missing-netrc",
        data_dir=tmp_path,
        require_earthdata=True,
    )
    assert result["ready"] is False
    assert result["checks"][-1]["status"] == "fail"


def test_doctor_accepts_nested_data_directory_not_created_yet(tmp_path: Path):
    result = product_cli.doctor(
        earthdata_path=tmp_path / "missing-netrc",
        data_dir=tmp_path / "future" / "nested" / "data",
        require_earthdata=False,
    )
    assert result["ready"] is True
    assert result["checks"][1]["status"] == "pass"


def test_inventory_emits_stable_json(monkeypatch, tmp_path: Path, capsys):
    aoi = tmp_path / "aoi.yaml"
    aoi.write_text(
        """name: test-aoi
description: test
geometry:
  type: Polygon
  coordinates:
    - [[-55.1, -7.0], [-55.0, -7.0], [-55.0, -7.1], [-55.1, -7.1], [-55.1, -7.0]]
"""
    )
    monkeypatch.setattr(product_cli, "search_gunw_pairs", lambda *args, **kwargs: [_pair()])

    result = product_cli.main(["inventory", str(aoi), "--tier", "provisional", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert result == 0
    assert payload["aoi"] == "test-aoi"
    assert payload["recommended_frame"]["track"] == 42
    assert payload["recommended_frame"]["direction"] == "DESCENDING"


def test_run_delegates_to_backward_compatible_benchmark(monkeypatch, tmp_path: Path):
    config = tmp_path / "config.yaml"
    config.write_text("name: placeholder\n")
    seen = []
    monkeypatch.setattr(product_cli, "benchmark_main", lambda argv: seen.extend(argv) or 0)

    assert product_cli.main(["run", str(config)]) == 0
    assert seen == [str(config)]


def test_build_stack_requires_track_and_frame_together(tmp_path: Path, capsys):
    result = product_cli.main(
        ["build-stack", "aoi.yaml", "--out", str(tmp_path / "stack.zarr"), "--track", "42"]
    )
    assert result == 2
    assert "--track and --frame" in capsys.readouterr().err


def test_build_stack_exposes_frozen_machine_readable_workflow(monkeypatch, tmp_path: Path, capsys):
    aoi = tmp_path / "aoi.yaml"
    aoi.write_text(
        """name: test-aoi
geometry:
  type: Polygon
  coordinates:
    - [[-55.1, -7.0], [-55.0, -7.0], [-55.0, -7.1], [-55.1, -7.1], [-55.1, -7.0]]
"""
    )
    calls = []
    monkeypatch.setattr(product_cli, "search_gunw_pairs", lambda *args, **kwargs: [_pair()])
    monkeypatch.setattr(
        product_cli.CoherenceStack,
        "build",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    output = tmp_path / "stack.zarr"

    result = product_cli.main(
        [
            "build-stack",
            str(aoi),
            "--out",
            str(output),
            "--track",
            "42",
            "--frame",
            "7",
            "--direction",
            "DESCENDING",
            "--min-pairs",
            "1",
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert result == 0
    assert payload["auto_selected"] is False
    assert payload["track"] == 42
    assert payload["pair_count"] == 1
    assert calls[0][1]["resolution_m"] == 20
