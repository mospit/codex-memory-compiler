from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from tests.support import FIXTURES_DIR, KBScriptTestCase
import compile as compile_module
from utils import parse_frontmatter


def make_session(
    session_id: str,
    *,
    title: str,
    context: str,
    keywords: list[str],
    task_ref: str | None = None,
    raw_body: str = "",
    full_text: str | None = None,
) -> SimpleNamespace:
    rendered = full_text or " ".join([title, context, *keywords, task_ref or ""])
    return SimpleNamespace(
        session_id=session_id,
        article_source="daily/2026-04-10.md",
        title=title,
        source_type="codex-summary",
        context=context,
        keywords=keywords,
        decisions=[],
        lessons=[],
        actions=[],
        workspace=None,
        repo=None,
        task_ref=task_ref,
        raw_body=raw_body,
        full_text=rendered,
    )


class CompileUnitTest(unittest.TestCase):
    def test_register_session_merges_via_existing_alias(self) -> None:
        aggregates: dict[str, compile_module.ConceptAggregate] = {}

        first_key = compile_module.register_session(
            aggregates,
            make_session(
                "alias-1",
                title="Platform Auth",
                context="Keep the platform auth rollout simple.",
                keywords=["platform", "authentication"],
            ),
        )
        second_key = compile_module.register_session(
            aggregates,
            make_session(
                "alias-2",
                title="Shared Auth Cleanup",
                context="Shared auth cleanup should align with the platform auth rollout.",
                keywords=["shared", "authentication"],
                task_ref="platform-auth",
            ),
        )

        self.assertEqual(first_key, second_key)
        aggregate = aggregates[first_key]
        self.assertEqual(aggregate.source_sessions, ["alias-1", "alias-2"])
        self.assertIn("Platform Auth", aggregate.aliases)
        self.assertIn("Shared Auth Cleanup", aggregate.aliases)


class CompileWorkflowTest(KBScriptTestCase):
    def test_compile_merges_repeated_sessions_into_one_concept(self) -> None:
        sessions = json.loads((FIXTURES_DIR / "duplicate_alias_sessions.json").read_text(encoding="utf-8"))
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
                "--task-ref",
                session["task_ref"],
                "--no-compile-trigger",
                now=session["now"],
            )
            self.assertEqual(result.returncode, 0, result.stderr)

        compile_result = self.run_script("compile.py", "--all", now="2026-04-10T09:15:00-05:00")
        self.assertEqual(compile_result.returncode, 0, compile_result.stderr)

        concept_files = list((self.kb_root / "knowledge" / "concepts").glob("*.md"))
        self.assertEqual(len(concept_files), 1)
        frontmatter, body = parse_frontmatter(concept_files[0].read_text(encoding="utf-8"))
        self.assertEqual(frontmatter.get("source_sessions"), ["alias-1", "alias-2"])
        self.assertIn("Platform Auth", frontmatter.get("aliases", []))
        self.assertIn("Shared Auth Cleanup", frontmatter.get("aliases", []))
        self.assertIn("## Evidence", body)

    def test_compile_creates_connection_after_second_cooccurrence_and_tracks_log_changes(self) -> None:
        first_ingest = self.run_script(
            "ingest.py",
            "--text",
            "We decided to keep API design stable during the authentication migration. The authentication migration depends on API design compatibility.",
            "--session-id",
            "cooccur-1",
            "--title",
            "API Design",
            "--source-type",
            "codex-summary",
            "--no-compile-trigger",
            now="2026-04-10T10:00:00-05:00",
        )
        self.assertEqual(first_ingest.returncode, 0, first_ingest.stderr)

        first_compile = self.run_script("compile.py", "--all", now="2026-04-10T10:05:00-05:00")
        self.assertEqual(first_compile.returncode, 0, first_compile.stderr)
        self.assertEqual(list((self.kb_root / "knowledge" / "connections").glob("*.md")), [])

        second_ingest = self.run_script(
            "ingest.py",
            "--text",
            "We will use authentication migration rollout with an API design checklist. API design must stay stable during authentication migration.",
            "--session-id",
            "cooccur-2",
            "--title",
            "Authentication Migration",
            "--source-type",
            "codex-summary",
            "--no-compile-trigger",
            now="2026-04-10T10:10:00-05:00",
        )
        self.assertEqual(second_ingest.returncode, 0, second_ingest.stderr)

        second_compile = self.run_script("compile.py", now="2026-04-10T10:15:00-05:00")
        self.assertEqual(second_compile.returncode, 0, second_compile.stderr)
        self.assertIn("Selected logs (1):", second_compile.stdout)
        self.assertIn("2026-04-10.md", second_compile.stdout)

        connection_files = list((self.kb_root / "knowledge" / "connections").glob("*.md"))
        self.assertEqual(len(connection_files), 1)
        frontmatter, _ = parse_frontmatter(connection_files[0].read_text(encoding="utf-8"))
        self.assertEqual(frontmatter.get("cooccurrence_count"), "2")
        self.assertEqual(frontmatter.get("source_sessions"), ["cooccur-1", "cooccur-2"])
