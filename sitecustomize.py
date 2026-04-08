"""Enable coverage subprocess tracking when COVERAGE_PROCESS_START is set."""

from __future__ import annotations

import os


if os.getenv("COVERAGE_PROCESS_START"):
    try:
        import coverage
    except ImportError:
        coverage = None
    if coverage is not None:
        coverage.process_startup()
