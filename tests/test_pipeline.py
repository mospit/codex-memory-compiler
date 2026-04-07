from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class PipelineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="memory-pipeline-test-"))
        for directory in ("daily", "knowledge/concepts", "knowledge/connections", "knowledge/qa", "reports", "scripts"):
            (self.temp_dir / directory).mkdir(parents=True, exist_ok=True)

        self.env = os.environ.copy()
        self.env["MEMORY_COMPILER_ROOT"] = str(self.temp_dir)

        self.context_file = self.temp_dir / "context.md"
        self.context_file.write_text(
            "**User:** Decided to migrate auth middleware and document deterministic fallback workflow.\n"
            "**Assistant:** Add compile and query sanity tests next.\n",
            encoding="utf-8",
        )

    def run_cmd(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, *args],
            cwd=ROOT,
            env=self.env,
            capture_output=True,
            text=True,
            check=True,
        )

    def test_deterministic_pipeline(self) -> None:
        self.run_cmd("scripts/ingest.py", "--file", str(self.context_file), "--session-id", "test-001", "--no-compile-trigger")

        daily_logs = sorted((self.temp_dir / "daily").glob("*.md"))
        self.assertTrue(daily_logs, "ingest should create at least one daily log")

        self.run_cmd("scripts/compile.py")
        index_path = self.temp_dir / "knowledge" / "index.md"
        self.assertTrue(index_path.exists(), "compile should produce knowledge/index.md")
        self.assertIn("[[concepts/", index_path.read_text(encoding="utf-8"))

        query_result = self.run_cmd("scripts/query.py", "What did I decide about auth middleware?")
        self.assertIn("Sources Consulted", query_result.stdout)

        self.run_cmd("scripts/lint.py", "--structural-only")
        reports = sorted((self.temp_dir / "reports").glob("lint-*.md"))
        self.assertTrue(reports, "lint should emit a report file")


if __name__ == "__main__":
    unittest.main()
