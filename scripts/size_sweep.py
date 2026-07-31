"""Minimum-detectable-size sweep on synthetic scenes — by width, not just area.

Two physical effects make narrow linear features harder than their area
suggests, and this sweep charts both:

1. Cluster support — a 1-px-wide trail of the same area has half the pixels
   of a 2-px road, so the min-cluster filter bites sooner.
2. Sub-pixel fill — a 5 m trail in a ~55 m pixel fills ~10% of each cell;
   the rest stays coherent forest, diluting the measured coherence drop
   (fill_fraction in the generator models this directly).

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

# ~55 m synthetic pixels -> ~0.305 ha per pixel.
PIXEL_AREA_HA = 0.305
LENGTHS_PX = [40, 24, 16, 12, 8, 6, 4, 3]
WIDTHS_PX = [2, 1]
FILLS = [1.0, 0.5, 0.25]

AOI = AreaOfInterest(
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


def detected(detector: V0FilterDetector, scene: SceneConfig) -> bool:
    stack = CoherenceStack(generate_scene(scene), AOI)
    for detection in detector.detect(stack):
        centroid = shape(detection.geometry).centroid
        if abs(centroid.x - (-55.0)) < 0.01 and abs(centroid.y - (-7.0)) < 0.01:
            return True
    return False


def main() -> int:
    detector = V0FilterDetector()
    print("minimum-detectable-size sweep (synthetic, v0 defaults)")
    print("area_ha = length_px * width_px * 0.305; DETECT/miss per fill fraction\n")
    print(f"{'width':>5} {'len':>4} {'area_ha':>8} | " + " ".join(f"fill={f:<4}" for f in FILLS))

    floors: dict[tuple[int, float], float] = {}
    for width in WIDTHS_PX:
        for length in LENGTHS_PX:
            area_ha = length * width * PIXEL_AREA_HA
            row = []
            for fill in FILLS:
                scene = SceneConfig(
                    seed=1000 + 7 * length + 3 * width + int(fill * 100),
                    disturbances=[
                        PlantedDisturbance(
                            id=f"sweep-{width}x{length}",
                            shape="line",
                            size_px=length,
                            width_px=width,
                            fill_fraction=fill,
                            from_step=5,
                        )
                    ],
                )
                hit = detected(detector, scene)
                row.append("DETECT " if hit else "miss   ")
                if hit:
                    key = (width, fill)
                    floors[key] = min(floors.get(key, float("inf")), area_ha)
            print(f"{width:>5} {length:>4} {area_ha:>8.1f} | " + " ".join(row))

    print("\nsmallest detected area (synthetic bound, not a claim):")
    for (width, fill), floor in sorted(floors.items()):
        print(f"  width {width} px, fill {fill:>4}: ~{floor:.1f} ha")
    undetectable = [(w, f) for w in WIDTHS_PX for f in FILLS if (w, f) not in floors]
    for width, fill in undetectable:
        print(f"  width {width} px, fill {fill:>4}: NOTHING detected — below the v0 floor")
    print("\nkill-criterion threshold: 2.0 ha. Narrow/diluted features are the honest gap.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
