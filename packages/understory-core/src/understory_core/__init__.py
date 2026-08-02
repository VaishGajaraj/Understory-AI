"""understory-core: NISAR data plumbing.

Granule discovery, retrieval, coherence stack construction, tiling, caching.
Application-agnostic by design — no forest-specific logic lives here.
"""

from importlib.metadata import version

from understory_core.aoi import AreaOfInterest
from understory_core.stack import CoherenceStack

__version__ = version("understory-core")

__all__ = ["AreaOfInterest", "CoherenceStack", "__version__"]
