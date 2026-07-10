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
