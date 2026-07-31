import numpy as np
from understory_detect.synthetic import (
    TOY_SCENE,
    PlantedDisturbance,
    SceneConfig,
    generate_scene,
    truth_features,
)
from understory_labels.events import DisturbanceEvent


def test_generation_is_deterministic():
    a = generate_scene(TOY_SCENE)
    b = generate_scene(TOY_SCENE)
    assert np.array_equal(a.coherence.values, b.coherence.values)


def test_planted_disturbance_lowers_coherence():
    scene = SceneConfig(
        disturbances=[PlantedDisturbance(id="d1", shape="blob", size_px=10, from_step=4)]
    )
    ds = generate_scene(scene)
    n = scene.n_pixels
    cy = cx = int(0.5 * (n - 1))
    inside_after = float(ds.coherence.values[5, cy, cx])
    inside_before = float(ds.coherence.values[2, cy, cx])
    assert inside_after < 0.4
    assert inside_before > 0.5


def test_transient_disturbance_is_single_step():
    scene = SceneConfig(
        disturbances=[
            PlantedDisturbance(id="d1", shape="blob", size_px=10, from_step=4, persistent=False)
        ]
    )
    ds = generate_scene(scene)
    n = scene.n_pixels
    cy = cx = int(0.5 * (n - 1))
    assert float(ds.coherence.values[4, cy, cx]) < 0.4
    assert float(ds.coherence.values[5, cy, cx]) > 0.5


def test_truth_features_validate_as_label_events():
    features = truth_features(TOY_SCENE)
    events = [DisturbanceEvent.from_feature(f) for f in features]
    statuses = {e.id: e.status for e in events}
    assert statuses["toy-road-001"] == "confirmed"  # persistent -> confirmed
    assert statuses["toy-rain-001"] == "rejected"  # transient -> rejected
    assert all(e.area_ha and e.area_ha > 0 for e in events)


def test_line_width_controls_footprint():
    from understory_detect.synthetic import _footprint

    narrow = PlantedDisturbance(id="n", shape="line", size_px=10, width_px=1)
    wide = PlantedDisturbance(id="w", shape="line", size_px=10, width_px=3)
    assert len(_footprint(narrow, 50)[0]) == 10
    assert len(_footprint(wide, 50)[0]) == 30


def test_fill_fraction_dilutes_coherence_drop():
    diluted = PlantedDisturbance(id="d", shape="blob", size_px=10, fill_fraction=0.25)
    full = PlantedDisturbance(id="f", shape="blob", size_px=10, fill_fraction=1.0)
    assert diluted.effective_coherence(0.7) == 0.25 * 0.2 + 0.75 * 0.7
    assert full.effective_coherence(0.7) == 0.2
    # The diluted scene's disturbed cells sit much closer to background.
    scene = SceneConfig(disturbances=[diluted])
    ds = generate_scene(scene)
    cy = cx = int(0.5 * (scene.n_pixels - 1))
    assert float(ds.coherence.values[6, cy, cx]) > 0.45


def test_edge_clipped_footprint_has_no_duplicate_pixels():
    """Clipping at the grid edge must not double-count cells — label areas
    are derived from the index count."""
    from understory_detect.synthetic import _footprint

    edge = PlantedDisturbance(id="e", shape="line", center=(0.02, 0.02), size_px=20, width_px=2)
    ys, xs = _footprint(edge, 100)
    assert len(ys) == len(set(zip(ys.tolist(), xs.tolist(), strict=True)))
