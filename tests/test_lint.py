from __future__ import annotations

from tests.support import FIXTURES_DIR, KBScriptTestCase


class LintBehaviorTest(KBScriptTestCase):
    def test_lint_detects_possible_conflicts_from_fixture(self) -> None:
        self.copy_fixture_tree(FIXTURES_DIR / "conflicting_kb")

        result = self.run_script("lint.py", now="2026-04-10T12:00:00-05:00")

        self.assertEqual(result.returncode, 0, result.stderr)
        report = (self.kb_root / "reports" / "lint-2026-04-10.md").read_text(encoding="utf-8")
        self.assertIn("Possible conflict with concepts/shared-auth-standard.md", report)

    def test_lint_flags_sparse_summary_fixture(self) -> None:
        self.copy_fixture_tree(FIXTURES_DIR / "sparse_summary_kb")

        result = self.run_script("lint.py", "--structural-only", now="2026-04-11T08:00:00-05:00")

        self.assertEqual(result.returncode, 0, result.stderr)
        report = (self.kb_root / "reports" / "lint-2026-04-11.md").read_text(encoding="utf-8")
        self.assertIn("Summary is missing or too weak", report)

    def test_lint_autofix_is_idempotent_on_second_run(self) -> None:
        self.copy_fixture_tree(FIXTURES_DIR / "broken_kb")

        first = self.run_script(
            "lint.py",
            "--structural-only",
            "--autofix",
            now="2026-04-10T12:10:00-05:00",
        )
        self.assertEqual(first.returncode, 1, first.stderr)
        first_report = (self.kb_root / "reports" / "lint-2026-04-10.md").read_text(encoding="utf-8")
        self.assertIn("Autofixes applied: 4", first_report)

        second = self.run_script(
            "lint.py",
            "--structural-only",
            "--autofix",
            now="2026-04-10T12:15:00-05:00",
        )
        self.assertEqual(second.returncode, 1, second.stderr)
        second_report = (self.kb_root / "reports" / "lint-2026-04-10.md").read_text(encoding="utf-8")
        self.assertIn("Autofixes applied: 0", second_report)

        platform_auth = (self.kb_root / "knowledge" / "concepts" / "platform-auth.md").read_text(encoding="utf-8")
        self.assertEqual(platform_auth.count("[[concepts/api-design]] - Added by lint autofix"), 1)
