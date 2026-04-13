from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests import support as _support  # noqa: F401
from utils import parse_daily_sessions, parse_frontmatter


class UtilsParsingTest(unittest.TestCase):
    def test_parse_frontmatter_handles_unclosed_block_as_plain_body(self) -> None:
        content = "---\ntitle: Broken Frontmatter\nsummary: missing closer\n# Body"

        frontmatter, body = parse_frontmatter(content)

        self.assertEqual(frontmatter, {})
        self.assertEqual(body, content)

    def test_parse_daily_sessions_generates_fallback_session_id_and_context_for_sparse_entry(self) -> None:
        with tempfile.TemporaryDirectory(prefix="utils-daily-") as temp_dir:
            log_path = Path(temp_dir) / "2026-04-12.md"
            log_path.write_text(
                "\n".join(
                    [
                        "# Daily Log: 2026-04-12",
                        "",
                        "## Sessions",
                        "",
                        "### Untitled Session (09:00)",
                        "",
                        "Random note without metadata",
                    ]
                ),
                encoding="utf-8",
            )

            sessions = parse_daily_sessions(log_path)

        self.assertEqual(len(sessions), 1)
        self.assertTrue(sessions[0].session_id.startswith("2026-04-12-untitled-session-"))
        self.assertEqual(sessions[0].context, "Random note without metadata")

    def test_parse_daily_sessions_extracts_structured_sections_and_line_refs(self) -> None:
        with tempfile.TemporaryDirectory(prefix="utils-structured-") as temp_dir:
            log_path = Path(temp_dir) / "2026-04-12.md"
            log_path.write_text(
                "\n".join(
                    [
                        "# Daily Log: 2026-04-12",
                        "",
                        "## Sessions",
                        "",
                        "### Structured Session (13:00)",
                        "",
                        "**Session ID:** structured-001",
                        "**Source Type:** codex-summary",
                        "**Title:** Structured Session",
                        "**Context:** Implement the new retrieval path.",
                        "**Date Context:** As of 2026-04-12 after fixture repair.",
                        "**Keywords:** retrieval, evidence",
                        "",
                        "**Key Exchanges:**",
                        "- Implement the new retrieval path.",
                        "",
                        "**Decisions Made:**",
                        "- Keep `--text` backward compatible.",
                        "",
                        "**Blockers:**",
                        "- Old sessions do not have line references.",
                        "",
                        "**Files Touched:**",
                        "- scripts/query.py",
                        "",
                        "**Tests Run:**",
                        "- py -3 -m unittest tests.test_query -v",
                        "",
                        "**Evidence Excerpts:**",
                        "- daily/2026-04-12.md:60 captured the beta model session.",
                        "",
                        "**Action Items:**",
                        "- [ ] Add decision records.",
                    ]
                ),
                encoding="utf-8",
            )

            sessions = parse_daily_sessions(log_path)

        self.assertEqual(len(sessions), 1)
        session = sessions[0]
        self.assertEqual(session.date_context, "As of 2026-04-12 after fixture repair.")
        self.assertEqual(session.blockers, ["Old sessions do not have line references."])
        self.assertEqual(session.files_touched, ["scripts/query.py"])
        self.assertEqual(session.tests_run, ["py -3 -m unittest tests.test_query -v"])
        self.assertEqual(session.evidence_excerpts, ["daily/2026-04-12.md:60 captured the beta model session."])
        self.assertEqual(session.actions, ["Add decision records."])
        self.assertTrue(session.context_line_number is not None)
        self.assertEqual(session.line_refs["tests_run"][0].line_number > session.context_line_number, True)
