from __future__ import annotations

import json
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


def normalize_text(text: str) -> str:
    return text.replace("\r\n", "\n").strip() + "\n"


class MemoryCompilerE2ETest(unittest.TestCase):
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

    def test_ingest_compile_query_and_lint_match_golden_files(self) -> None:
        sessions = json.loads((FIXTURES_DIR / "e2e_sessions.json").read_text(encoding="utf-8"))
        for session in sessions:
            result = self.run_script(
                "ingest.py",
                "--text",
                session["text"],
                "--session-id",
                session["session_id"],
                "--title",
                session["title"],
                "--source-type",
                session["source_type"],
                "--workspace",
                session["workspace"],
                "--repo",
                session["repo"],
                "--task-ref",
                session["task_ref"],
                "--no-compile-trigger",
                now=session["now"],
            )
            self.assertEqual(result.returncode, 0, result.stderr)

        compile_result = self.run_script("compile.py", "--all", now="2026-04-08T10:00:00-05:00")
        self.assertEqual(compile_result.returncode, 0, compile_result.stderr)

        expected_files = [
            ("daily/2026-04-08.md", "e2e/daily/2026-04-08.md"),
            (
                "knowledge/concepts/authentication-migration.md",
                "e2e/knowledge/concepts/authentication-migration.md",
            ),
            ("knowledge/concepts/api-design.md", "e2e/knowledge/concepts/api-design.md"),
            (
                "knowledge/connections/api-design__authentication-migration.md",
                "e2e/knowledge/connections/api-design__authentication-migration.md",
            ),
            ("knowledge/index.md", "e2e/knowledge/index.md"),
            ("knowledge/log.md", "e2e/knowledge/log.md"),
        ]
        for actual_rel, golden_rel in expected_files:
            self.assert_matches_golden(self.kb_root / actual_rel, GOLDEN_DIR / golden_rel)

        query_result = self.run_script(
            "query.py",
            "What did I decide about auth migration?",
            "--explain",
            now="2026-04-08T10:05:00-05:00",
        )
        self.assertEqual(query_result.returncode, 0, query_result.stderr)
        self.assertEqual(
            normalize_text(query_result.stdout),
            normalize_text((GOLDEN_DIR / "e2e" / "query-auth-migration.txt").read_text(encoding="utf-8")),
        )

        lint_result = self.run_script("lint.py", "--autofix", now="2026-04-08T10:10:00-05:00")
        self.assertEqual(lint_result.returncode, 0, lint_result.stderr)
        self.assert_matches_golden(
            self.kb_root / "reports" / "lint-2026-04-08.md",
            GOLDEN_DIR / "e2e" / "reports" / "lint-2026-04-08.md",
        )

        second_compile = self.run_script("compile.py", now="2026-04-08T10:20:00-05:00")
        self.assertEqual(second_compile.returncode, 0, second_compile.stderr)
        self.assertIn("Nothing to compile - all daily logs are up to date.", second_compile.stdout)

    def test_lint_autofix_updates_index_and_backlinks_on_broken_fixture(self) -> None:
        self.copy_fixture_tree(FIXTURES_DIR / "broken_kb")

        result = self.run_script(
            "lint.py",
            "--structural-only",
            "--autofix",
            now="2026-04-09T12:00:00-05:00",
        )
        self.assertEqual(result.returncode, 1, result.stdout)

        report = (self.kb_root / "reports" / "lint-2026-04-09.md").read_text(encoding="utf-8")
        self.assertIn("Broken link: [[concepts/missing-page]]", report)
        self.assertIn("Possible duplicate concept cluster", report)
        self.assertIn("missing source_sessions or source_logs", report)
        self.assertIn("Connection article has no source sessions or zero cooccurrence count", report)
        self.assertNotIn("Index rows do not match", report)
        self.assertNotIn("but not vice versa", report)

        index_text = (self.kb_root / "knowledge" / "index.md").read_text(encoding="utf-8")
        self.assertNotIn("stale-row", index_text)

        platform_auth = (self.kb_root / "knowledge" / "concepts" / "platform-auth.md").read_text(encoding="utf-8")
        self.assertIn("[[concepts/api-design]] - Added by lint autofix", platform_auth)


if __name__ == "__main__":
    unittest.main()
