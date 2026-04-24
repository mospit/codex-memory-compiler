"""Compatibility shim for the package config module."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_package_module = importlib.import_module("codex_memory_compiler.config")
_package_module = importlib.reload(_package_module)

for _name in [name for name in dir(_package_module) if not name.startswith("_")]:
    globals()[_name] = getattr(_package_module, _name)

__all__ = [name for name in globals() if not name.startswith("_")]
