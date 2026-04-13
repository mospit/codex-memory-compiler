from __future__ import annotations

from pathlib import Path

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

    def test_lint_flags_thin_codex_summary_sessions(self) -> None:
        daily_dir = self.kb_root / "daily"
        daily_dir.mkdir(parents=True, exist_ok=True)
        (daily_dir / "2026-04-12.md").write_text(
            "\n".join(
                [
                    "# Daily Log: 2026-04-12",
                    "",
                    "## Sessions",
                    "",
                    "### Thin Summary (09:00)",
                    "",
                    "**Session ID:** thin-summary-001",
                    "**Source Type:** codex-summary",
                    "**Title:** Thin Summary",
                    "**Context:** Worked on the portal memory flow.",
                    "**Keywords:** portal, memory",
                    "",
                    "**Key Exchanges:**",
                    "- Worked on the portal memory flow.",
                ]
            ),
            encoding="utf-8",
        )

        result = self.run_script("lint.py", "--structural-only", now="2026-04-12T09:30:00-05:00")

        self.assertEqual(result.returncode, 0, result.stderr)
        report = (self.kb_root / "reports" / "lint-2026-04-12.md").read_text(encoding="utf-8")
        self.assertIn("has only generic context and no explicit decisions, validation, blockers, evidence, or next steps", report)

    def test_lint_exempts_dashboard_from_orphan_and_missing_backlink_noise(self) -> None:
        structured_context = "\n".join(
            [
                "## Summary",
                "- Reviewed the auth rollout follow-up list.",
                "",
                "## Decisions",
                "- Keep the shared auth redirect guard.",
                "",
                "## Next Steps",
                "- Add the dashboard landing page.",
            ]
        )

        ingest_result = self.run_script(
            "ingest.py",
            "--text",
            structured_context,
            "--session-id",
            "dashboard-lint-001",
            "--title",
            "Dashboard Lint Session",
            "--source-type",
            "codex-summary",
            "--no-compile",
            "--no-lint",
            "--no-compile-trigger",
            now="2026-04-12T11:00:00-05:00",
        )
        self.assertEqual(ingest_result.returncode, 0, ingest_result.stderr)

        compile_result = self.run_script("compile.py", "--all", now="2026-04-12T11:05:00-05:00")
        self.assertEqual(compile_result.returncode, 0, compile_result.stderr)

        result = self.run_script("lint.py", "--structural-only", now="2026-04-12T11:10:00-05:00")
        self.assertEqual(result.returncode, 0, result.stderr)
        report = (self.kb_root / "reports" / "lint-2026-04-12.md").read_text(encoding="utf-8")
        self.assertNotIn("Orphan page: no other articles link to [[dashboards/open-followups]]", report)
        self.assertNotIn("[[dashboards/open-followups]] links to [[concepts/", report)
        self.assertNotIn("[[dashboards/open-followups]] links to [[decisions/", report)
