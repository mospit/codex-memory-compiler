"""Compatibility shim for ingest command."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

if __name__ == "__main__":
    from codex_memory_compiler.cli import main as _cli_main

    raise SystemExit(_cli_main(["ingest", *sys.argv[1:]], legacy_default_root=True))

sys.modules[__name__] = importlib.import_module("codex_memory_compiler.ingest")
