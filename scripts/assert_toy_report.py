"""CI assertion on the toy benchmark report.

The toy stack is constructed so a correct v0 detector scores perfectly:
the persistent road is found, the transient rain blob is filtered. Any drop
below perfection on synthetic data is a regression, not a tuning question.

Usage: uv run python scripts/assert_toy_report.py benchmarks/toy/reports/toy.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    report = json.loads(Path(sys.argv[1]).read_text())
    failures = []
    if report["event_precision"] != 1.0:
        failures.append(f"precision {report['event_precision']} != 1.0")
    if report["event_recall"] != 1.0:
        failures.append(f"recall {report['event_recall']} != 1.0")
    if report["false_positives"] != 0:
        failures.append(f"{report['false_positives']} false positives (rain blob leaked through?)")

    if failures:
        print("toy benchmark regression:", "; ".join(failures), file=sys.stderr)
        return 1
    print(
        f"toy benchmark ok: precision {report['event_precision']}, "
        f"recall {report['event_recall']}, "
        f"latency {report['median_detection_latency_days']} days"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
