"""understory-labels: the open labeled disturbance-event library."""

from importlib.metadata import version

from understory_labels.events import DateWindow, DisturbanceEvent, load_collection

__version__ = version("understory-labels")
SCHEMA_VERSION = "0.1.0"

__all__ = ["DateWindow", "DisturbanceEvent", "SCHEMA_VERSION", "__version__", "load_collection"]
