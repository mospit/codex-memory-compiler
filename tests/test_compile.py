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
                "--no-compile",
                "--no-lint",
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
            "--no-compile",
            "--no-lint",
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
            "--no-compile",
            "--no-lint",
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

    def test_compile_uses_structured_evidence_validation_and_emits_decision_records(self) -> None:
        structured_context = "\n".join(
            [
                "## Summary",
                "- Implement the auth redirect guard rollout.",
                "",
                "## Decisions",
                "- Keep the shared auth redirect guard.",
                "",
                "## Validation",
                "- py -3 -m unittest tests.test_query -v",
                "",
                "## Evidence",
                "- Verified redirect guard activation on the staging portal.",
                "",
                "## Next Steps",
                "- Add decision-aware query ranking.",
            ]
        )

        ingest_result = self.run_script(
            "ingest.py",
            "--text",
            structured_context,
            "--session-id",
            "structured-compile-001",
            "--title",
            "Structured Compile Session",
            "--source-type",
            "codex-summary",
            "--no-compile",
            "--no-lint",
            "--no-compile-trigger",
            now="2026-04-12T14:00:00-05:00",
        )
        self.assertEqual(ingest_result.returncode, 0, ingest_result.stderr)

        compile_result = self.run_script("compile.py", "--all", now="2026-04-12T14:05:00-05:00")
        self.assertEqual(compile_result.returncode, 0, compile_result.stderr)

        concept_files = list((self.kb_root / "knowledge" / "concepts").glob("*.md"))
        self.assertEqual(len(concept_files), 1)
        concept_text = concept_files[0].read_text(encoding="utf-8")
        self.assertIn("## Validation", concept_text)
        self.assertIn("py -3 -m unittest tests.test_query -v", concept_text)
        self.assertIn("daily/2026-04-12.md:", concept_text)

        decision_files = list((self.kb_root / "knowledge" / "decisions").glob("*.md"))
        self.assertEqual(len(decision_files), 1)
        decision_frontmatter, decision_body = parse_frontmatter(decision_files[0].read_text(encoding="utf-8"))
        self.assertEqual(decision_frontmatter.get("source_sessions"), ["structured-compile-001"])
        self.assertIn("## Decision", decision_body)
        self.assertIn("## Rationale / Evidence", decision_body)

        dashboard_path = self.kb_root / "knowledge" / "dashboards" / "open-followups.md"
        self.assertTrue(dashboard_path.exists())
        dashboard_frontmatter, dashboard_body = parse_frontmatter(dashboard_path.read_text(encoding="utf-8"))
        self.assertEqual(dashboard_frontmatter.get("title"), "Open Follow-Ups")
        self.assertEqual(dashboard_frontmatter.get("source_sessions"), ["structured-compile-001"])
        self.assertIn("Generated by codex-memory-compiler", dashboard_body)
        self.assertIn("## Open Follow-Ups", dashboard_body)
        self.assertIn("## Recent Decisions", dashboard_body)
        self.assertIn("- [[concepts/", dashboard_body)
        self.assertIn(f"- [[decisions/{decision_files[0].stem}]]", dashboard_body)
        self.assertNotIn("No follow-up actions captured yet.", dashboard_body)

        index_text = (self.kb_root / "knowledge" / "index.md").read_text(encoding="utf-8")
        self.assertIn("| [[dashboards/open-followups]] | dashboard |", index_text)

    def test_compile_keeps_decision_evidence_scoped_to_the_matching_decision(self) -> None:
        structured_context = "\n".join(
            [
                "## Summary",
                "- Reviewed two rollout decisions in one session.",
                "",
                "## Decisions",
                "- Keep the shared auth redirect guard.",
                "- Keep the shared API contract.",
                "",
                "## Validation",
                "- Verified the redirect guard checklist.",
                "",
                "## Evidence",
                "- Confirmed the shared contract still matches the rollout assumptions.",
            ]
        )

        ingest_result = self.run_script(
            "ingest.py",
            "--text",
            structured_context,
            "--session-id",
            "structured-compile-002",
            "--title",
            "Structured Multi Decision Session",
            "--source-type",
            "codex-summary",
            "--no-compile",
            "--no-lint",
            "--no-compile-trigger",
            now="2026-04-12T14:10:00-05:00",
        )
        self.assertEqual(ingest_result.returncode, 0, ingest_result.stderr)

        compile_result = self.run_script("compile.py", "--all", now="2026-04-12T14:15:00-05:00")
        self.assertEqual(compile_result.returncode, 0, compile_result.stderr)

        decision_files = sorted((self.kb_root / "knowledge" / "decisions").glob("*.md"))
        self.assertEqual(len(decision_files), 2)

        contract_body = next(
            parse_frontmatter(path.read_text(encoding="utf-8"))[1]
            for path in decision_files
            if "shared-api-contract" in path.stem
        )
        self.assertIn("Keep the shared API contract.", contract_body)
        self.assertNotIn("Keep the shared auth redirect guard.", contract_body)

    def test_compile_sanitizes_decision_titles_with_wikilinks(self) -> None:
        structured_context = "\n".join(
            [
                "## Summary",
                "- Planned the Obsidian landing page.",
                "",
                "## Decisions",
                "- Add `knowledge/dashboards/` with `[[dashboards/open-followups]]` as the landing page.",
            ]
        )

        ingest_result = self.run_script(
            "ingest.py",
            "--text",
            structured_context,
            "--session-id",
            "structured-compile-003",
            "--title",
            "Structured Wikilink Decision Session",
            "--source-type",
            "codex-summary",
            "--no-compile",
            "--no-lint",
            "--no-compile-trigger",
            now="2026-04-12T14:20:00-05:00",
        )
        self.assertEqual(ingest_result.returncode, 0, ingest_result.stderr)

        compile_result = self.run_script("compile.py", "--all", now="2026-04-12T14:25:00-05:00")
        self.assertEqual(compile_result.returncode, 0, compile_result.stderr)

        decision_path = next((self.kb_root / "knowledge" / "decisions").glob("*.md"))
        decision_text = decision_path.read_text(encoding="utf-8")
        self.assertIn("dashboards/open-followups", decision_text)
        self.assertNotIn("[[dashb...", decision_text)

    def test_compile_emits_goal_records_and_decision_relation_backlinks(self) -> None:
        first_context = "\n".join(
            [
                "## Goal",
                "- Start the Prism closed beta.",
                "",
                "## Summary",
                "- Locked the founder invite launch policy.",
                "",
                "## Current Status",
                "- Two-path launch model is implemented locally.",
                "",
                "## Decisions",
                "- Keep founder invites manual copy-link only for launch.",
                "",
                "## Files",
                "- apps/portal/lib/beta-access.ts",
                "",
                "## Validation",
                "- npm --prefix apps/portal run test:policy",
                "",
                "## Verification State",
                "- Policy tests and lint pass; production launch env verification still pending.",
                "",
                "## Next Steps",
                "- Set production launch env and rerun check:launch.",
                "",
                "## Open Questions",
                "- Can the production portal be verified without interrupting the dev server?",
            ]
        )

        second_context = "\n".join(
            [
                "## Goal",
                "- Start the Prism closed beta.",
                "",
                "## Summary",
                "- Finalized the canonical founder invite handling.",
                "",
                "## Current Status",
                "- Canonical founder invite handling is implemented and should replace the earlier invite note.",
                "",
                "## Decisions",
                "- Keep the canonical founder invite grant model for launch.",
                "",
                "## Decision Links",
                "- supersedes: [[decisions/keep-founder-invite-manual-copy-link-only-launch]]",
                "- implemented_by: apps/portal/lib/beta-access.ts",
                "- blocked_by: Production Clerk and launch env setup",
                "",
                "## Next Steps",
                "- Verify production launch env and start the closed beta.",
            ]
        )

        first_ingest = self.run_script(
            "ingest.py",
            "--text",
            first_context,
            "--session-id",
            "goal-compile-001",
            "--title",
            "Closed Beta Goal Session One",
            "--source-type",
            "codex-summary",
            "--task-ref",
            "closed-beta-launch",
            "--no-compile",
            "--no-lint",
            "--no-compile-trigger",
            now="2026-04-12T15:00:00-05:00",
        )
        self.assertEqual(first_ingest.returncode, 0, first_ingest.stderr)

        second_ingest = self.run_script(
            "ingest.py",
            "--text",
            second_context,
            "--session-id",
            "goal-compile-002",
            "--title",
            "Closed Beta Goal Session Two",
            "--source-type",
            "codex-summary",
            "--task-ref",
            "closed-beta-launch",
            "--no-compile",
            "--no-lint",
            "--no-compile-trigger",
            now="2026-04-12T15:10:00-05:00",
        )
        self.assertEqual(second_ingest.returncode, 0, second_ingest.stderr)

        compile_result = self.run_script("compile.py", "--all", now="2026-04-12T15:15:00-05:00")
        self.assertEqual(compile_result.returncode, 0, compile_result.stderr)

        goal_path = self.kb_root / "knowledge" / "goals" / "closed-beta-launch.md"
        self.assertTrue(goal_path.exists())
        goal_frontmatter, goal_body = parse_frontmatter(goal_path.read_text(encoding="utf-8"))
        self.assertEqual(goal_frontmatter.get("current_status"), "Canonical founder invite handling is implemented and should replace the earlier invite note.")
        self.assertIn("## Next Steps", goal_body)
        self.assertIn("## Open Questions", goal_body)
        self.assertIn("apps/portal/lib/beta-access.ts", goal_body)

        new_decision = self.kb_root / "knowledge" / "decisions" / "keep-canonical-founder-invite-grant-model-launch.md"
        old_decision = self.kb_root / "knowledge" / "decisions" / "keep-founder-invite-manual-copy-link-only-launch.md"
        self.assertTrue(new_decision.exists())
        self.assertTrue(old_decision.exists())

        new_frontmatter, new_body = parse_frontmatter(new_decision.read_text(encoding="utf-8"))
        old_frontmatter, old_body = parse_frontmatter(old_decision.read_text(encoding="utf-8"))
        self.assertEqual(new_frontmatter.get("supersedes"), ["keep-founder-invite-manual-copy-link-only-launch"])
        self.assertEqual(old_frontmatter.get("superseded_by"), ["keep-canonical-founder-invite-grant-model-launch"])
        self.assertIn("implemented_by: apps/portal/lib/beta-access.ts", new_body)
        self.assertIn("superseded_by: [[decisions/keep-canonical-founder-invite-grant-model-launch]]", old_body)
