from __future__ import annotations

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
            "--no-compile-trigger",
            now="2026-04-10T09:15:00-05:00",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        daily_text = (self.kb_root / "daily" / "2026-04-10.md").read_text(encoding="utf-8")
        self.assertIn("**Source Type:** codex-chat", daily_text)
        self.assertIn("**Session ID:** malformed-chat-002", daily_text)
        self.assertIn("Need to capture this conversation even without explicit speaker labels.", daily_text)
