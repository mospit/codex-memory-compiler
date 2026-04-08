"""Query the knowledge base via deterministic index-guided retrieval."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from config import LOG_FILE, QA_DIR, now_iso
from utils import (
    MANAGED_BY,
    extract_keywords,
    load_state,
    read_index_entries,
    read_markdown_article,
    rebuild_index,
    save_state,
    slugify,
    tokenize,
    trim_sentence,
    write_markdown_article,
)


@dataclass(slots=True)
class RankedArticle:
    """A shortlisted article with index and content scores."""

    link: str
    path: Path
    article_type: str
    summary: str
    keywords: list[str]
    sources: list[str]
    updated: str
    index_score: int
    content_score: int
    reasons: list[str]

    @property
    def total_score(self) -> int:
        return self.index_score + self.content_score


def score_index_entry(question_tokens: list[str], entry) -> tuple[int, list[str]]:
    """Score an index row before opening the article."""
    reasons: list[str] = []
    score = 0

    keyword_counts = Counter(tokenize(" ".join(entry.keywords)))
    keyword_hits = sum(keyword_counts[token] for token in question_tokens)
    if keyword_hits:
        score += keyword_hits * 4
        reasons.append(f"keyword hits={keyword_hits}")

    link_tokens = set(tokenize(entry.link.replace("/", " ")))
    link_hits = sum(1 for token in question_tokens if token in link_tokens)
    if link_hits:
        score += link_hits * 3
        reasons.append(f"path hits={link_hits}")

    summary_counts = Counter(tokenize(entry.summary))
    summary_hits = sum(summary_counts[token] for token in question_tokens)
    if summary_hits:
        score += summary_hits * 2
        reasons.append(f"summary hits={summary_hits}")

    return score, reasons


def shortlist_articles(question: str, limit: int = 8) -> list[RankedArticle]:
    """Read the index first, then shortlist candidate articles."""
    entries = read_index_entries()
    if not entries:
        return []

    question_tokens = tokenize(question)
    ranked: list[RankedArticle] = []
    for entry in entries:
        index_score, reasons = score_index_entry(question_tokens, entry)
        if index_score <= 0 or not entry.path.exists():
            continue
        ranked.append(
            RankedArticle(
                link=entry.link,
                path=entry.path,
                article_type=entry.article_type,
                summary=entry.summary,
                keywords=entry.keywords,
                sources=entry.sources,
                updated=entry.updated,
                index_score=index_score,
                content_score=0,
                reasons=reasons,
            )
        )

    ranked.sort(key=lambda article: (-article.index_score, article.link))
    return ranked[:limit]


def score_article_content(question_tokens: list[str], path: Path) -> tuple[int, str]:
    """Open the article and score the actual content."""
    frontmatter, body = read_markdown_article(path)
    summary = str(frontmatter.get("summary") or "")
    combined = " ".join([summary, body])
    counts = Counter(tokenize(combined))
    score = sum(counts[token] for token in question_tokens)

    snippet_candidates: list[tuple[int, str]] = []
    current_section = ""
    for line in body.splitlines():
        clean = line.strip()
        if not clean or clean.startswith("#") or clean.startswith("---"):
            if clean.startswith("## "):
                current_section = clean[3:].strip().lower()
            continue
        if current_section in {"related concepts", "sources"}:
            continue
        if clean.startswith("- [["):
            continue
        clean = clean[2:] if clean.startswith("- ") else clean
        line_score = sum(1 for token in question_tokens if token in tokenize(clean))
        if line_score:
            snippet_candidates.append((line_score, clean))

    if snippet_candidates:
        snippet_candidates.sort(key=lambda item: (-item[0], len(item[1])))
        return score, trim_sentence(snippet_candidates[0][1], 180)

    if summary:
        return score, trim_sentence(summary, 180)

    fallback = trim_sentence(body.strip().splitlines()[0] if body.strip() else "No concise summary available.", 180)
    return score, fallback


def select_articles(question: str, shortlist_limit: int = 8, consult_limit: int = 4) -> list[RankedArticle]:
    """Shortlist from the index, then rerank by actual article content."""
    question_tokens = tokenize(question)
    shortlist = shortlist_articles(question, limit=shortlist_limit)
    consulted: list[RankedArticle] = []

    for candidate in shortlist:
        content_score, snippet = score_article_content(question_tokens, candidate.path)
        reasons = [*candidate.reasons, f"content hits={content_score}"]
        consulted.append(
            RankedArticle(
                link=candidate.link,
                path=candidate.path,
                article_type=candidate.article_type,
                summary=snippet,
                keywords=candidate.keywords,
                sources=candidate.sources,
                updated=candidate.updated,
                index_score=candidate.index_score,
                content_score=content_score,
                reasons=reasons,
            )
        )

    consulted.sort(key=lambda article: (-article.total_score, -article.index_score, article.link))
    return consulted[:consult_limit]


def confidence_label(articles: list[RankedArticle]) -> str:
    """Return a coarse confidence label based on ranking strength."""
    if not articles:
        return "low"

    top_score = articles[0].total_score
    supporting = sum(1 for article in articles if article.total_score > 0)
    if top_score >= 12 and supporting >= 2:
        return "high"
    if top_score >= 7:
        return "medium"
    return "low"


def build_answer(question: str, articles: list[RankedArticle], *, explain: bool) -> str:
    """Build a deterministic answer from shortlisted articles."""
    if not articles:
        return (
            "I could not find relevant compiled knowledge for that question. "
            "Compile recent daily logs first with `uv run python scripts/compile.py`."
        )

    confidence = confidence_label(articles)
    lines = ["## Answer", "", f"Confidence: {confidence}", ""]
    lines.append("Most relevant compiled knowledge:")
    lines.append("")
    for article in articles:
        lines.append(f"- [[{article.link}]] ({article.article_type}): {article.summary}")

    lines.extend(
        [
            "",
            "## Synthesis",
            "",
            "The shortlist clusters around the cited pages above. Treat those articles as the current canonical memory, and recompile after new sessions if the answer feels incomplete.",
            "",
            "## Sources Consulted",
        ]
    )
    lines.extend(f"- [[{article.link}]]" for article in articles)

    if explain:
        lines.extend(["", "## Retrieval Notes", ""])
        for article in articles:
            lines.append(
                f"- [[{article.link}]]: total={article.total_score}, index={article.index_score}, content={article.content_score}; {', '.join(article.reasons)}"
            )

    return "\n".join(lines)


def file_back_answer(question: str, answer: str, articles: list[RankedArticle]) -> Path:
    """Persist a Q&A article and rebuild the index."""
    QA_DIR.mkdir(parents=True, exist_ok=True)
    slug = slugify(question) or "query-answer"
    qa_path = QA_DIR / f"{slug}.md"
    consulted = [article.link for article in articles]
    confidence = confidence_label(articles)
    keywords = extract_keywords((question, 5), limit=6)

    source_section = [f"- [[{item}]]" for item in consulted] if consulted else ["- (none)"]
    body_sections = [
        f"# Q: {question}",
        "",
        answer,
        "",
        "## Sources Consulted",
        *source_section,
        "",
        "## Follow-Up Questions",
        "- Which daily logs should be recompiled to improve coverage?",
        "- Does this answer need a new connection article?",
    ]

    frontmatter = {
        "managed_by": MANAGED_BY,
        "title": f"Q: {question}",
        "question": question,
        "summary": trim_sentence(f"Filed answer for: {question}", 140),
        "keywords": keywords,
        "consulted": consulted,
        "confidence": confidence,
        "filed": now_iso()[:10],
        "updated": now_iso()[:10],
    }
    write_markdown_article(qa_path, frontmatter, "\n".join(body_sections))
    rebuild_index()

    with open(LOG_FILE, "a", encoding="utf-8") as handle:
        consulted_links = ", ".join(f"[[{item}]]" for item in consulted) if consulted else "(none)"
        handle.write(f"## [{now_iso()}] query (filed)\n")
        handle.write(f"- Question: {question}\n")
        handle.write(f"- Consulted: {consulted_links}\n")
        handle.write(f"- Filed to: [[qa/{qa_path.stem}]]\n\n")

    return qa_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Query the personal knowledge base")
    parser.add_argument("question", help="The question to ask")
    parser.add_argument("--file-back", action="store_true", help="Save answer as knowledge/qa article")
    parser.add_argument("--explain", action="store_true", help="Show retrieval notes and scores")
    args = parser.parse_args()

    articles = select_articles(args.question)
    answer = build_answer(args.question, articles, explain=args.explain)

    print(f"Question: {args.question}")
    print(f"File back: {'yes' if args.file_back else 'no'}")
    print(f"Explain: {'yes' if args.explain else 'no'}")
    print("-" * 60)
    print(answer)

    if args.file_back:
        qa_path = file_back_answer(args.question, answer, articles)
        print("\n" + "-" * 60)
        print(f"Answer filed to {qa_path.relative_to(QA_DIR.parent)}")

    state = load_state()
    state["query_count"] = state.get("query_count", 0) + 1
    save_state(state)


if __name__ == "__main__":
    main()
