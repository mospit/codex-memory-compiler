from __future__ import annotations

import json
import unittest

from tests.support import FIXTURES_DIR, GOLDEN_DIR, KBScriptTestCase, normalize_text


class MemoryCompilerE2ETest(KBScriptTestCase):

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

    def test_codex_chat_file_ingest_can_compile_and_lint_in_one_command(self) -> None:
        transcript = FIXTURES_DIR / "codex_chat_sample.md"
        result = self.run_script(
            "ingest.py",
            "--codex-chat-file",
            str(transcript),
            "--session-id",
            "codex-chat-001",
            "--title",
            "Codex Chat Capture",
            "--workspace",
            "D:/projects/product/codex-memory-compiler",
            "--repo",
            "mospit/codex-memory-compiler",
            "--task-ref",
            "dogfood-002",
            "--compile",
            "--lint",
            now="2026-04-09T09:00:00-05:00",
        )
        self.assertEqual(result.returncode, 0, result.stderr)

        daily_text = (self.kb_root / "daily" / "2026-04-09.md").read_text(encoding="utf-8")
        self.assertIn("**Source Type:** codex-chat", daily_text)
        self.assertIn("**Session ID:** codex-chat-001", daily_text)
        self.assertIn("Codex Chat Capture", daily_text)

        concept_files = list((self.kb_root / "knowledge" / "concepts").glob("*.md"))
        self.assertEqual(len(concept_files), 1)
        concept_stem = concept_files[0].stem

        index_text = (self.kb_root / "knowledge" / "index.md").read_text(encoding="utf-8")
        self.assertIn(f"[[concepts/{concept_stem}]]", index_text)

        query_result = self.run_script(
            "query.py",
            "How should I test the project on itself?",
            "--explain",
            now="2026-04-09T09:10:00-05:00",
        )
        self.assertEqual(query_result.returncode, 0, query_result.stderr)
        self.assertIn(f"[[concepts/{concept_stem}]]", query_result.stdout)

        lint_report = (self.kb_root / "reports" / "lint-2026-04-09.md").read_text(encoding="utf-8")
        self.assertIn("Warnings: 1", lint_report)
        self.assertIn("Orphan page", lint_report)


if __name__ == "__main__":
    unittest.main()
