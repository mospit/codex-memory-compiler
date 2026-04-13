from __future__ import annotations

from pathlib import Path

from tests.support import FIXTURES_DIR, KBScriptTestCase


class IngestCLITest(KBScriptTestCase):
    def test_requires_one_input_mode(self) -> None:
        result = self.run_script("ingest.py", now="2026-04-10T09:00:00-05:00")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Provide one of --text, --file, or --codex-chat-file", result.stderr)

    def test_rejects_multiple_input_modes(self) -> None:
        result = self.run_script(
            "ingest.py",
            "--text",
            "Testing invalid flag combinations.",
            "--file",
            str(FIXTURES_DIR / "codex_chat_sample.md"),
            now="2026-04-10T09:05:00-05:00",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Provide only one of --text, --file, or --codex-chat-file", result.stderr)

    def test_rejects_missing_context_file(self) -> None:
        result = self.run_script(
            "ingest.py",
            "--codex-chat-file",
            str(FIXTURES_DIR / "missing-codex-chat.md"),
            now="2026-04-10T09:10:00-05:00",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Context file not found", result.stderr)

    def test_malformed_codex_chat_falls_back_to_note_capture(self) -> None:
        result = self.run_script(
            "ingest.py",
            "--codex-chat-file",
            str(FIXTURES_DIR / "malformed_codex_chat_sample.md"),
            "--session-id",
            "malformed-chat-002",
            "--no-compile",
            "--no-lint",
            "--no-compile-trigger",
            now="2026-04-10T09:15:00-05:00",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        daily_text = (self.kb_root / "daily" / "2026-04-10.md").read_text(encoding="utf-8")
        self.assertIn("**Source Type:** codex-chat", daily_text)
        self.assertIn("**Session ID:** malformed-chat-002", daily_text)
        self.assertIn("Need to capture this conversation even without explicit speaker labels.", daily_text)

    def test_ingest_compiles_and_lints_by_default(self) -> None:
        result = self.run_script(
            "ingest.py",
            "--text",
            "We decided to keep platform auth stable while updating the API design checklist.",
            "--session-id",
            "auto-maintenance-001",
            "--title",
            "Automatic maintenance",
            "--source-type",
            "codex-summary",
            now="2026-04-10T09:20:00-05:00",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.kb_root / "knowledge" / "index.md").exists())
        self.assertTrue((self.kb_root / "reports" / "lint-2026-04-10.md").exists())

    def test_structured_text_ingest_preserves_all_supported_sections(self) -> None:
        structured = "\n".join(
            [
                "## Summary",
                "- Locked the beta access grant model.",
                "",
                "## Decisions",
                "- Keep request-access payment gated on approval.",
                "",
                "## Blockers",
                "- Clerk production redirect validation is still pending.",
                "",
                "## Files",
                "- docs/plans/closed-beta.md",
                "",
                "## Validation",
                "- not run: docs-only change",
                "",
                "## Evidence",
                "- Reviewed the latest admission model draft with the founder.",
                "",
                "## Next Steps",
                "- Implement betaAccessGrant persistence in the portal.",
                "",
                "## Date Context",
                "- State captured as of 2026-04-12.",
            ]
        )

        result = self.run_script(
            "ingest.py",
            "--text",
            structured,
            "--session-id",
            "structured-text-001",
            "--title",
            "Structured Text Capture",
            "--source-type",
            "codex-summary",
            "--no-compile",
            "--no-lint",
            "--no-compile-trigger",
            now="2026-04-10T09:30:00-05:00",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        daily_text = (self.kb_root / "daily" / "2026-04-10.md").read_text(encoding="utf-8")
        self.assertIn("**Context:** Locked the beta access grant model.", daily_text)
        self.assertIn("**Date Context:** State captured as of 2026-04-12.", daily_text)
        self.assertIn("**Blockers:**", daily_text)
        self.assertIn("**Files Touched:**", daily_text)
        self.assertIn("**Tests Run:**", daily_text)
        self.assertIn("**Evidence Excerpts:**", daily_text)
        self.assertIn("- [ ] Implement betaAccessGrant persistence in the portal.", daily_text)

    def test_structured_file_ingest_preserves_all_supported_sections(self) -> None:
        context_path = Path(self.temp_dir.name) / "structured-session.md"
        context_path.write_text(
            "\n".join(
                [
                    "## Summary",
                    "- Verified the compiler can emit decision records.",
                    "",
                    "## Decisions",
                    "- Add decision articles only from explicit Decisions items.",
                    "",
                    "## Validation",
                    "- py -3 -m unittest tests.test_compile -v",
                    "",
                    "## Evidence",
                    "- Confirmed decision provenance includes daily log refs.",
                    "",
                    "## Next Steps",
                    "- Refresh the e2e golden fixtures for decision articles.",
                ]
            ),
            encoding="utf-8",
        )

        result = self.run_script(
            "ingest.py",
            "--file",
            str(context_path),
            "--session-id",
            "structured-file-001",
            "--title",
            "Structured File Capture",
            "--source-type",
            "codex-summary",
            "--no-compile",
            "--no-lint",
            "--no-compile-trigger",
            now="2026-04-10T09:35:00-05:00",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        daily_text = (self.kb_root / "daily" / "2026-04-10.md").read_text(encoding="utf-8")
        self.assertIn("**Context:** Verified the compiler can emit decision records.", daily_text)
        self.assertIn("- py -3 -m unittest tests.test_compile -v", daily_text)
        self.assertIn("- Confirmed decision provenance includes daily log refs.", daily_text)
        self.assertIn("- [ ] Refresh the e2e golden fixtures for decision articles.", daily_text)

    def test_flag_only_structured_ingest_builds_goal_status_and_code_anchors(self) -> None:
        result = self.run_script(
            "ingest.py",
            "--goal",
            "Start the Prism closed beta",
            "--current-status",
            "Two-path launch model is implemented locally.",
            "--decision",
            "Keep founder invites manual copy-link only for launch.",
            "--decision-link",
            "blocked_by: Production Clerk and launch env setup",
            "--file-touched",
            "apps/portal/lib/beta-access.ts",
            "--validation",
            "npm --prefix apps/portal run test:policy",
            "--verification-state",
            "Policy tests and lint pass; production launch env verification still pending.",
            "--next-step",
            "Set production launch env and rerun check:launch.",
            "--open-question",
            "Can the production portal be verified without interrupting the local dev server?",
            "--session-id",
            "structured-flags-001",
            "--title",
            "Structured Flags Capture",
            "--source-type",
            "codex-summary",
            "--no-compile",
            "--no-lint",
            "--no-compile-trigger",
            now="2026-04-10T09:40:00-05:00",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        daily_text = (self.kb_root / "daily" / "2026-04-10.md").read_text(encoding="utf-8")
        self.assertIn("**Goal:** Start the Prism closed beta", daily_text)
        self.assertIn("**Current Status:** Two-path launch model is implemented locally.", daily_text)
        self.assertIn("**Decision Links:**", daily_text)
        self.assertIn("**Files Touched:**", daily_text)
        self.assertIn("**Verification State:** Policy tests and lint pass; production launch env verification still pending.", daily_text)
        self.assertIn("**Open Questions:**", daily_text)
