from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tests.support import FIXTURES_DIR, KBScriptTestCase
import query as query_module
from utils import write_markdown_article


class QueryUnitTest(unittest.TestCase):
    def test_score_index_entry_rewards_keywords_paths_and_summary(self) -> None:
        entry = SimpleNamespace(
            link="concepts/authentication-migration",
            keywords=["authentication", "migration"],
            summary="Keep API design stable during authentication migration.",
        )

        score, reasons = query_module.score_index_entry(["authentication", "migration", "design"], entry)

        self.assertEqual(score, 20)
        self.assertIn("keyword hits=2", reasons)
        self.assertIn("path hits=2", reasons)
        self.assertIn("summary hits=3", reasons)

    def test_select_articles_reranks_shortlist_by_content_score(self) -> None:
        with tempfile.TemporaryDirectory(prefix="query-ranking-") as temp_dir:
            temp_root = Path(temp_dir)
            strong_path = temp_root / "strong.md"
            weak_path = temp_root / "weak.md"
            write_markdown_article(
                strong_path,
                {"summary": "Fallback summary", "updated": "2026-04-10"},
                "\n".join(
                    [
                        "# Strong",
                        "",
                        "## Decisions",
                        "- Use authentication migration with a strict API design checklist.",
                    ]
                ),
            )
            write_markdown_article(
                weak_path,
                {"summary": "Mentions migration once.", "updated": "2026-04-10"},
                "\n".join(["# Weak", "", "## Decisions", "- Note the migration."]),
            )

            shortlist = [
                query_module.RankedArticle(
                    link="concepts/weak",
                    path=weak_path,
                    article_type="concept",
                    summary="weak",
                    keywords=[],
                    sources=[],
                    updated="2026-04-10",
                    index_score=7,
                    content_score=0,
                    reasons=["keyword hits=2"],
                ),
                query_module.RankedArticle(
                    link="concepts/strong",
                    path=strong_path,
                    article_type="concept",
                    summary="strong",
                    keywords=[],
                    sources=[],
                    updated="2026-04-10",
                    index_score=9,
                    content_score=0,
                    reasons=["keyword hits=2"],
                ),
            ]

            with patch.object(query_module, "shortlist_articles", return_value=shortlist):
                selected = query_module.select_articles(
                    "How should authentication migration handle API design?",
                    consult_limit=2,
                )

        self.assertEqual(selected[0].link, "concepts/strong")
        self.assertGreater(selected[0].content_score, selected[1].content_score)

    def test_score_article_content_ignores_related_and_sources_sections(self) -> None:
        with tempfile.TemporaryDirectory(prefix="query-content-") as temp_dir:
            article_path = Path(temp_dir) / "article.md"
            write_markdown_article(
                article_path,
                {"summary": "Authentication migration summary", "updated": "2026-04-10"},
                "\n".join(
                    [
                        "# Authentication Migration",
                        "",
                        "## Decisions",
                        "- Keep API design stable during authentication migration.",
                        "",
                        "## Evidence",
                        "- daily/2026-04-10.md:42 / `session-1` (codex-summary): Verified the redirect guard in production.",
                        "",
                        "## Related Concepts",
                        "- [[concepts/api-design]] - API design authentication migration API design",
                        "",
                        "## Sources",
                        "- [[daily/2026-04-10]]",
                    ]
                ),
            )
            signals = query_module.score_article_content(
                ["authentication", "migration", "design"],
                article_path,
            )

        self.assertGreaterEqual(signals.content_score, 3)
        self.assertEqual(signals.snippet, "daily/2026-04-10.md:42 / `session-1` (codex-summary): Verified the redirect guard in production.")
        self.assertTrue(signals.has_concrete_evidence)
        self.assertEqual(len(signals.supporting_excerpts), 2)

    def test_confidence_label_thresholds(self) -> None:
        high = [
            query_module.RankedArticle("a", Path("a.md"), "concept", "Strong summary", [], [], "2026-04-10", 8, 5, [], ["daily/2026-04-10.md:20: evidence"], False, True),
            query_module.RankedArticle("b", Path("b.md"), "concept", "Support summary", [], [], "2026-04-09", 5, 2, [], ["daily/2026-04-09.md:10: evidence"], False, True),
        ]
        medium = [query_module.RankedArticle("a", Path("a.md"), "concept", "Strong summary", [], [], "2026-04-10", 4, 3, [], [], False, False)]
        low = [query_module.RankedArticle("a", Path("a.md"), "concept", "Weak...", [], [], "2026-04-08", 2, 1, [], [], True, False)]

        self.assertEqual(query_module.confidence_label("What did we decide about auth migration?", high), "high")
        self.assertEqual(query_module.confidence_label("What changed?", medium), "medium")
        self.assertEqual(query_module.confidence_label("latest auth state", low), "low")
        self.assertEqual(query_module.confidence_label("What changed?", []), "low")

    def test_build_answer_with_evidence_and_penalties(self) -> None:
        article = query_module.RankedArticle(
            "decisions/keep-structured-text-compatible",
            Path("decision.md"),
            "decision",
            "Keep --text compatible with structured headings.",
            [],
            [],
            "2026-04-10",
            10,
            6,
            ["decision intent boost=6", "content hits=6"],
            ["daily/2026-04-10.md:42 / `s1` (codex-summary): Keep --text compatible with structured headings."],
            False,
            True,
        )

        answer = query_module.build_answer(
            "What did we decide about ingest?",
            [article],
            explain=True,
            include_evidence=True,
        )

        self.assertIn("## Supporting Excerpts", answer)
        self.assertIn("daily/2026-04-10.md:42", answer)
        self.assertIn("Confidence penalties:", answer)

    def test_build_answer_handles_no_results(self) -> None:
        answer = query_module.build_answer("Where is the missing context?", [], explain=True)

        self.assertIn("I could not find relevant compiled knowledge", answer)
        self.assertIn("Compile recent daily logs first", answer)

    def test_select_articles_prefers_decision_records_for_decision_questions(self) -> None:
        with tempfile.TemporaryDirectory(prefix="query-decision-") as temp_dir:
            temp_root = Path(temp_dir)
            decision_path = temp_root / "decision.md"
            concept_path = temp_root / "concept.md"
            write_markdown_article(
                decision_path,
                {"summary": "Keep the shared auth redirect guard.", "updated": "2026-04-10"},
                "\n".join(
                    [
                        "# Keep Shared Auth Redirect Guard",
                        "",
                        "## Decision",
                        "- Keep the shared auth redirect guard.",
                        "",
                        "## Rationale / Evidence",
                        "- daily/2026-04-10.md:20 / `s1` (codex-summary): Verified the guard path.",
                    ]
                ),
            )
            write_markdown_article(
                concept_path,
                {"summary": "Authentication migration overview.", "updated": "2026-04-10"},
                "\n".join(["# Authentication Migration", "", "## Decisions", "- Keep the shared auth redirect guard."]),
            )

            shortlist = [
                query_module.RankedArticle(
                    link="concepts/authentication-migration",
                    path=concept_path,
                    article_type="concept",
                    summary="overview",
                    keywords=[],
                    sources=[],
                    updated="2026-04-10",
                    index_score=10,
                    content_score=0,
                    reasons=["keyword hits=2"],
                ),
                query_module.RankedArticle(
                    link="decisions/keep-shared-auth-redirect-guard",
                    path=decision_path,
                    article_type="decision",
                    summary="decision",
                    keywords=[],
                    sources=[],
                    updated="2026-04-10",
                    index_score=10,
                    content_score=0,
                    reasons=["keyword hits=2"],
                ),
            ]

            with patch.object(query_module, "shortlist_articles", return_value=shortlist):
                selected = query_module.select_articles(
                    "What did we decide about the redirect guard?",
                    consult_limit=2,
                )

        self.assertEqual(selected[0].article_type, "decision")

    def test_score_article_content_prefers_decision_line_for_decision_articles(self) -> None:
        with tempfile.TemporaryDirectory(prefix="query-decision-snippet-") as temp_dir:
            article_path = Path(temp_dir) / "decision.md"
            write_markdown_article(
                article_path,
                {"summary": "Keep the shared auth redirect guard.", "updated": "2026-04-10"},
                "\n".join(
                    [
                        "# Keep Shared Auth Redirect Guard",
                        "",
                        "## Decision",
                        "- Keep the shared auth redirect guard.",
                        "",
                        "## Rationale / Evidence",
                        "- daily/2026-04-10.md:20 / `s1` (codex-summary): Verified the guard path in staging.",
                    ]
                ),
            )

            signals = query_module.score_article_content(
                ["decide", "redirect", "guard"],
                article_path,
            )

        self.assertEqual(signals.snippet, "Keep the shared auth redirect guard.")
        self.assertEqual(
            signals.supporting_excerpts[0],
            "daily/2026-04-10.md:20 / `s1` (codex-summary): Verified the guard path in staging.",
        )

    def test_select_articles_penalizes_superseded_decisions_for_current_state_questions(self) -> None:
        with tempfile.TemporaryDirectory(prefix="query-superseded-") as temp_dir:
            temp_root = Path(temp_dir)
            old_path = temp_root / "old-decision.md"
            new_path = temp_root / "new-decision.md"
            write_markdown_article(
                old_path,
                {
                    "summary": "Keep founder invites manual copy-link only for launch.",
                    "updated": "2026-04-12",
                    "superseded_by": ["keep-canonical-founder-invite-grant-model-for-launch"],
                },
                "\n".join(
                    [
                        "# Old Decision",
                        "",
                        "## Decision",
                        "- Keep founder invites manual copy-link only for launch.",
                    ]
                ),
            )
            write_markdown_article(
                new_path,
                {
                    "summary": "Keep the canonical founder invite grant model for launch.",
                    "updated": "2026-04-12",
                    "current_status": "Implemented locally and ready for launch verification.",
                },
                "\n".join(
                    [
                        "# New Decision",
                        "",
                        "## Decision",
                        "- Keep the canonical founder invite grant model for launch.",
                        "",
                        "## Current Status",
                        "- Implemented locally and ready for launch verification.",
                    ]
                ),
            )

            shortlist = [
                query_module.RankedArticle(
                    link="decisions/old-decision",
                    path=old_path,
                    article_type="decision",
                    summary="old",
                    keywords=[],
                    sources=[],
                    updated="2026-04-12",
                    index_score=10,
                    content_score=0,
                    reasons=["keyword hits=2"],
                ),
                query_module.RankedArticle(
                    link="decisions/new-decision",
                    path=new_path,
                    article_type="decision",
                    summary="new",
                    keywords=[],
                    sources=[],
                    updated="2026-04-12",
                    index_score=10,
                    content_score=0,
                    reasons=["keyword hits=2"],
                ),
            ]

            with patch.object(query_module, "shortlist_articles", return_value=shortlist):
                selected = query_module.select_articles(
                    "What is the current decision for founder invite launch state?",
                    consult_limit=2,
                )

        self.assertEqual(selected[0].link, "decisions/new-decision")
        self.assertIn("superseded penalty=1", selected[1].reasons)

    def test_build_answer_plan_brief_surfaces_status_and_next_steps(self) -> None:
        article = query_module.RankedArticle(
            "goals/closed-beta-launch",
            Path("goal.md"),
            "goal",
            "Two-path launch model is implemented locally.",
            [],
            [],
            "2026-04-12",
            12,
            8,
            ["goal planning boost=8", "content hits=8"],
            ["daily/2026-04-12.md:203 / `s1` (codex-summary): Implemented the two-path launch model locally."],
            False,
            True,
            metadata={
                "current_status": "Two-path launch model is implemented locally.",
                "next_steps": ["Set production launch env and rerun check:launch."],
                "open_questions": ["Can production launch verification run without interrupting the dev server?"],
            },
        )

        answer = query_module.build_answer(
            "What are the next steps to proceed with the closed beta?",
            [article],
            explain=True,
            include_evidence=False,
        )

        self.assertIn("## Current Goal State", answer)
        self.assertIn("## Next Steps", answer)
        self.assertIn("## Open Questions", answer)
        self.assertIn("[[goals/closed-beta-launch]] - Two-path launch model is implemented locally.", answer)


class QueryWorkflowTest(KBScriptTestCase):
    def test_query_returns_fallback_for_no_result_fixture(self) -> None:
        self.copy_fixture_tree(FIXTURES_DIR / "no_result_query_kb")

        result = self.run_script(
            "query.py",
            "How should I handle authentication migration risk?",
            now="2026-04-10T11:00:00-05:00",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("I could not find relevant compiled knowledge", result.stdout)
