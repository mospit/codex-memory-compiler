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
                        "## Related Concepts",
                        "- [[concepts/api-design]] - API design authentication migration API design",
                        "",
                        "## Sources",
                        "- [[daily/2026-04-10]]",
                    ]
                ),
            )
            score, snippet = query_module.score_article_content(
                ["authentication", "migration", "design"],
                article_path,
            )

        self.assertGreaterEqual(score, 3)
        self.assertEqual(snippet, "Keep API design stable during authentication migration.")

    def test_confidence_label_thresholds(self) -> None:
        high = [
            query_module.RankedArticle("a", Path("a.md"), "concept", "", [], [], "", 8, 5, []),
            query_module.RankedArticle("b", Path("b.md"), "concept", "", [], [], "", 5, 2, []),
        ]
        medium = [query_module.RankedArticle("a", Path("a.md"), "concept", "", [], [], "", 4, 3, [])]
        low = [query_module.RankedArticle("a", Path("a.md"), "concept", "", [], [], "", 2, 1, [])]

        self.assertEqual(query_module.confidence_label(high), "high")
        self.assertEqual(query_module.confidence_label(medium), "medium")
        self.assertEqual(query_module.confidence_label(low), "low")
        self.assertEqual(query_module.confidence_label([]), "low")

    def test_build_answer_handles_no_results(self) -> None:
        answer = query_module.build_answer("Where is the missing context?", [], explain=True)

        self.assertIn("I could not find relevant compiled knowledge", answer)
        self.assertIn("Compile recent daily logs first", answer)


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
