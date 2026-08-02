"""understory-detect: baselines, detectors, filters, and the scoring harness."""

from importlib.metadata import version

from understory_detect.interface import Detection, Detector

__version__ = version("understory-detect")

__all__ = ["Detection", "Detector", "__version__"]
