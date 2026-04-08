from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from model_adapter import ModelAdapterError, get_model_adapter


class ModelAdapterTest(unittest.TestCase):
    def test_get_model_adapter_prefers_explicit_provider(self) -> None:
        with patch.dict(os.environ, {"KB_MODEL_PROVIDER": "env-provider"}):
            adapter = get_model_adapter("explicit-provider")

        self.assertEqual(adapter.provider, "explicit-provider")

    def test_default_adapter_raises_clear_error(self) -> None:
        adapter = get_model_adapter()

        with self.assertRaises(ModelAdapterError) as raised:
            adapter.complete("Summarize the session")

        self.assertIn("No model adapter configured", str(raised.exception))
