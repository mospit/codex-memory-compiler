from __future__ import annotations

import importlib
import os
import unittest
from unittest.mock import patch

import config as config_module


class ConfigTest(unittest.TestCase):
    def test_now_helpers_use_kb_now_override(self) -> None:
        with patch.dict(os.environ, {"KB_NOW": "2026-04-10T14:30:00-05:00", "KB_TIMEZONE": "America/Chicago"}):
            config = importlib.reload(config_module)
            try:
                self.assertEqual(config.now_iso(), "2026-04-10T14:30:00-05:00")
                self.assertEqual(config.today_iso(), "2026-04-10")
            finally:
                importlib.reload(config_module)

    def test_now_dt_attaches_configured_timezone_to_naive_override(self) -> None:
        with patch.dict(os.environ, {"KB_NOW": "2026-04-10T14:30:00", "KB_TIMEZONE": "America/Chicago"}):
            config = importlib.reload(config_module)
            try:
                self.assertEqual(str(config.now_dt().tzinfo), "America/Chicago")
            finally:
                importlib.reload(config_module)
