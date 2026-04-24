"""Thin adapter boundary for optional model-backed operations.

Core workflows in this repo should work without any model integration. This
module exists so model-enhanced behavior can be added without coupling the
rest of the codebase to a specific SDK.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


class ModelAdapterError(RuntimeError):
    """Raised when model-backed operations are requested but unavailable."""


@dataclass(slots=True)
class ModelAdapter:
    """Interface for optional model-backed completion.

    Implementations can wrap any provider. The default adapter intentionally
    fails with clear guidance so deterministic fallback paths remain primary.
    """

    provider: str = "none"

    def complete(self, prompt: str) -> str:
        raise ModelAdapterError(
            "No model adapter configured. Use deterministic mode or run this task "
            "through Codex app with repository skills."
        )


def get_model_adapter(provider: str | None = None) -> ModelAdapter:
    """Return the configured adapter.

    Provider resolution order:
    1) explicit function arg
    2) KB_MODEL_PROVIDER environment variable
    3) default: "none"
    """

    chosen = (provider or os.getenv("KB_MODEL_PROVIDER") or "none").strip().lower()
    return ModelAdapter(provider=chosen)
