"""One-line logging setup shared by every CLI.

Default: warnings only, quiet pipelines. -v: INFO from understory packages
(fetch progress, scene-guard suppressions, stack writes). -vv: DEBUG plus
dependency chatter.
"""

from __future__ import annotations

import logging


def setup_logging(verbosity: int = 0) -> None:
    level = logging.WARNING if verbosity == 0 else logging.INFO if verbosity == 1 else logging.DEBUG
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    if verbosity == 1:
        # INFO for our packages, keep third-party libraries at WARNING.
        logging.getLogger().setLevel(logging.WARNING)
        for prefix in ("understory_core", "understory_detect", "understory_labels"):
            logging.getLogger(prefix).setLevel(logging.INFO)
