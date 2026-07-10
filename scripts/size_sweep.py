"""Minimum-detectable-size sweep on synthetic scenes.

Plants disturbances of decreasing size into fresh synthetic scenes and asks
the v0 detector to find them. Charts where detection fails — the synthetic
lower bound on minimum detectable event size, and the tool for tuning filter
thresholds before real controlled-disturbance ground truth exists.

Synthetic results are scaffolding, never claims: the published curve comes
from the eastern-woodland controlled disturbances.

Usage: uv run python scripts/size_sweep.py
"""

from __future__ import annotations

from shapely.geometry import shape
from understory_core.aoi import AreaOfInterest
from understory_core.stack import CoherenceStack
from understory_detect.detectors import V0FilterDetector
from understory_detect.synthetic import PlantedDisturbance, SceneConfig, generate_scene

# Line lengths to sweep (2 px wide); pixel is ~55 m so area ~= 0.61 ha per
# 2-px column. Sizes chosen to bracket the 2 ha kill-criterion threshold.
SIZES_PX = [40, 24, 16, 12, 8, 6, 4, 3]


def sweep() -> list[tuple[float, bool]]:
    aoi = AreaOfInterest(
        name="size-sweep",
        geometry={
            "type": "Polygon",
            "coordinates": [
                [
                    [-55.025, -7.025],
                    [-54.975, -7.025],
                    [-54.975, -6.975],
                    [-55.025, -6.975],
                    [-55.025, -7.025],
                ]
            ],
        },
    )
    detector = V0FilterDetector()
    results = []
    for size_px in SIZES_PX:
        scene = SceneConfig(
            seed=1000 + size_px,  # fresh noise per run; deterministic overall
            disturbances=[
                PlantedDisturbance(
                    id=f"sweep-{size_px}px", shape="line", size_px=size_px, from_step=5
                )
            ],
        )
        stack = CoherenceStack(generate_scene(scene), aoi)
        detections = detector.detect(stack)
        planted_area_ha = size_px * 2 * 0.305  # 2-px-wide line, ~55 m pixels
        found = any(
            shape(d.geometry).centroid.distance(shape(_center_point()).centroid) < 0.01
            for d in detections
        )
        results.append((planted_area_ha, found))
        print(
            f"  {size_px:3d} px (~{planted_area_ha:5.1f} ha): "
            f"{'DETECTED' if found else 'missed'} ({len(detections)} detections)"
        )
    return results


def _center_point() -> dict:
    return {"type": "Point", "coordinates": [-55.0, -7.0]}


def main() -> int:
    print("minimum-detectable-size sweep (synthetic, v0 detector defaults):")
    results = sweep()
    detected = [area for area, found in results if found]
    if detected:
        print(f"\nsmallest detected (synthetic): ~{min(detected):.1f} ha")
        print("kill-criterion threshold: 2.0 ha — synthetic bound only, not a claim")
    else:
        print("\nnothing detected — detector or generator is broken")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
