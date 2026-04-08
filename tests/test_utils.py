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
