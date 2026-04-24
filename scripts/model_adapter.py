"""Compatibility shim for the package model adapter."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

sys.modules[__name__] = importlib.import_module("codex_memory_compiler.model_adapter")
