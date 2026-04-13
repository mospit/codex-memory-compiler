from __future__ import annotations

import unittest

from tests.support import FIXTURES_DIR
from flush import build_structured_entry, parse_dialogue_turns, parse_note_lines
from utils import derive_title_from_text


class FlushParserTest(unittest.TestCase):
    def test_parse_dialogue_turns_handles_multiline_markdown_chat(self) -> None:
        transcript = (FIXTURES_DIR / "codex_chat_sample.md").read_text(encoding="utf-8")
        user_turns, assistant_turns = parse_dialogue_turns(transcript)

        self.assertEqual(len(user_turns), 2)
        self.assertEqual(len(assistant_turns), 2)
        self.assertIn("I want to test this project on itself.", user_turns[0])
        self.assertIn("The repo is local, and I want a Codex-first path.", user_turns[0])
        self.assertIn("Use `uv sync` first.", assistant_turns[0])
        self.assertIn("Then compile and query the knowledge base.", assistant_turns[1])

    def test_parse_dialogue_turns_handles_repeated_speakers_and_ignores_boilerplate(self) -> None:
        transcript = "\n".join(
            [
                "User: First request",
                "still the first request",
                "",
                "User: Second request",
                "**Assistant:** Captured via codex-chat ingest workflow.",
                "Assistant: First answer",
                "Assistant: Second answer",
            ]
        )
        user_turns, assistant_turns = parse_dialogue_turns(transcript)

        self.assertEqual(user_turns, ["First request\nstill the first request", "Second request"])
        self.assertEqual(assistant_turns, ["First answer", "Second answer"])

    def test_build_structured_entry_falls_back_to_note_lines_for_malformed_transcript(self) -> None:
        context = (FIXTURES_DIR / "malformed_codex_chat_sample.md").read_text(encoding="utf-8")
        note_lines = parse_note_lines(context)
        structured, derived_title = build_structured_entry(
            context,
            session_id="malformed-chat-001",
            title=None,
            source_type="codex-chat",
            workspace=None,
            repo=None,
            task_ref=None,
        )

        expected_context = note_lines[0]
        self.assertEqual(derived_title, derive_title_from_text(expected_context))
        self.assertIn(f"**Context:** {expected_context}", structured)
        self.assertIn("- Prefer keeping unittest and adding coverage gates.", structured)
        self.assertIn("- Next: add CI coverage checks after the local suite is stable.", structured)

    def test_build_structured_entry_preserves_structured_summary_sections(self) -> None:
        context = "\n".join(
            [
                "## Summary",
                "- Implemented structured ingest parsing.",
                "- Added evidence-backed query output.",
                "",
                "## Decisions",
                "- Keep --text compatible with richer headings.",
                "",
                "## Blockers",
                "- Missing historical evidence in older sessions.",
                "",
                "## Files",
                "- scripts/flush.py",
                "- scripts/query.py",
                "",
                "## Validation",
                "- py -3 -m unittest tests.test_flush -v",
                "",
                "## Evidence",
                "- daily/2026-04-12.md:60 shows the beta admission model session.",
                "",
                "## Next Steps",
                "- Add first-class decision records.",
                "",
                "## Date Context",
                "- As of 2026-04-12 after fixture repair.",
            ]
        )

        structured, derived_title = build_structured_entry(
            context,
            session_id="structured-001",
            title="Structured Summary",
            source_type="codex-summary",
            workspace="D:/work/repo",
            repo="example/repo",
            task_ref="TASK-1",
        )

        self.assertEqual(derived_title, "Structured Summary")
        self.assertIn("**Date Context:** As of 2026-04-12 after fixture repair.", structured)
        self.assertIn("**Blockers:**", structured)
        self.assertIn("**Files Touched:**", structured)
        self.assertIn("**Tests Run:**", structured)
        self.assertIn("**Evidence Excerpts:**", structured)
        self.assertIn("**Action Items:**", structured)
        self.assertIn("- scripts/flush.py", structured)
        self.assertIn("- py -3 -m unittest tests.test_flush -v", structured)
