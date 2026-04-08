from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"
GOLDEN_DIR = FIXTURES_DIR / "golden"
SCRIPT_DIR = REPO_ROOT / "scripts"

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))


def normalize_text(text: str) -> str:
    return text.replace("\r\n", "\n").strip() + "\n"


class KBScriptTestCase(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="codex-memory-compiler-tests-")
        self.kb_root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def run_script(self, script_name: str, *args: str, now: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["KB_ROOT_DIR"] = str(self.kb_root)
        env["KB_NOW"] = now
        pythonpath = env.get("PYTHONPATH")
        env["PYTHONPATH"] = (
            f"{REPO_ROOT}{os.pathsep}{pythonpath}" if pythonpath else str(REPO_ROOT)
        )
        return subprocess.run(
            [sys.executable, str(SCRIPT_DIR / script_name), *args],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    def assert_matches_golden(self, actual_path: Path, golden_path: Path) -> None:
        actual = normalize_text(actual_path.read_text(encoding="utf-8"))
        expected = normalize_text(golden_path.read_text(encoding="utf-8"))
        self.assertEqual(actual, expected, actual_path.as_posix())

    def copy_fixture_tree(self, source: Path) -> None:
        for item in source.iterdir():
            destination = self.kb_root / item.name
            if item.is_dir():
                shutil.copytree(item, destination)
            else:
                shutil.copy2(item, destination)
