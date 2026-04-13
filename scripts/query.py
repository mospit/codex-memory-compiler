"""Query the knowledge base via deterministic index-guided retrieval."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from config import LOG_FILE, QA_DIR, now_iso
from utils import (
    MANAGED_BY,
    extract_keywords,
    is_weak_summary,
    load_state,
    parse_article_sections,
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
    supporting_excerpts: list[str] = field(default_factory=list)
    weak_summary: bool = False
    has_concrete_evidence: bool = False
    metadata: dict[str, object] = field(default_factory=dict)

    @property
    def total_score(self) -> int:
        return self.index_score + self.content_score


@dataclass(slots=True)
class ArticleSignals:
    """Article content scoring and evidence signals."""

    content_score: int
    snippet: str
    supporting_excerpts: list[str]
    weak_summary: bool
    has_concrete_evidence: bool
    metadata: dict[str, object]
    score_reasons: list[str]


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


def is_decision_question(question: str) -> bool:
    """Return whether the question is primarily asking for a decision."""
    lowered = question.lower()
    decision_phrases = ("what did we decide", "why did we decide", "decision", "decided", "chosen")
    return any(phrase in lowered for phrase in decision_phrases)


def is_planning_question(question: str) -> bool:
    """Return whether the question is asking for plan/status/next-step guidance."""
    lowered = question.lower()
    planning_phrases = (
        "next step",
        "next steps",
        "what should we do next",
        "how should we proceed",
        "how do we proceed",
        "proceed",
        "plan",
        "blocker",
        "blocked",
        "open question",
        "open questions",
        "current status",
        "status",
    )
    return any(phrase in lowered for phrase in planning_phrases)


def shortlist_articles(question: str, limit: int = 8) -> list[RankedArticle]:
    """Read the index first, then shortlist candidate articles."""
    entries = read_index_entries()
    if not entries:
        return []

    question_tokens = tokenize(question)
    ranked: list[RankedArticle] = []
    for entry in entries:
        index_score, reasons = score_index_entry(question_tokens, entry)
        if entry.article_type == "decision" and is_decision_question(question):
            index_score += 6
            reasons.append("decision intent boost=6")
        if entry.article_type == "goal" and is_planning_question(question):
            index_score += 8
            reasons.append("goal planning boost=8")
        if entry.article_type == "decision" and (is_planning_question(question) or is_temporal_question(question)):
            index_score += 3
            reasons.append("current decision boost=3")
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
                supporting_excerpts=[],
                weak_summary=is_weak_summary(entry.summary),
                has_concrete_evidence=False,
                metadata={},
            )
        )

    ranked.sort(key=lambda article: (-article.index_score, article.link))
    return ranked[:limit]


def score_section_line(question_tokens: list[str], text: str, *, section: str) -> int:
    """Score a line inside a specific article section."""
    token_hits = sum(1 for token in question_tokens if token in tokenize(text))
    section_bonus = {
        "evidence": 4,
        "validation": 3,
        "decisions": 2,
        "decision": 2,
        "rationale / evidence": 4,
    }.get(section, 0)
    return token_hits + section_bonus if token_hits else 0


def excerpt_section_rank(section: str) -> int:
    """Return a stable priority for evidence-like sections."""
    return {
        "evidence": 4,
        "rationale / evidence": 4,
        "validation": 3,
        "decision": 2,
        "decisions": 2,
    }.get(section, 0)


def metadata_list(frontmatter: dict, key: str) -> list[str]:
    """Return a normalized metadata list from frontmatter."""
    value = frontmatter.get(key)
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def score_metadata_fields(question_tokens: list[str], frontmatter: dict) -> tuple[int, dict[str, object], list[str]]:
    """Score retrieval-relevant frontmatter fields."""
    metadata = {
        "current_status": str(frontmatter.get("current_status") or "").strip(),
        "next_steps": metadata_list(frontmatter, "next_steps"),
        "open_questions": metadata_list(frontmatter, "open_questions"),
        "verification_state": str(frontmatter.get("verification_state") or "").strip(),
        "files_touched": metadata_list(frontmatter, "files_touched"),
        "tests_run": metadata_list(frontmatter, "tests_run"),
        "superseded_by": metadata_list(frontmatter, "superseded_by"),
        "supersedes": metadata_list(frontmatter, "supersedes"),
        "implemented_by": metadata_list(frontmatter, "implemented_by"),
        "blocked_by": metadata_list(frontmatter, "blocked_by"),
    }

    score = 0
    reasons: list[str] = []
    field_map = {
        "current_status": [metadata["current_status"]] if metadata["current_status"] else [],
        "next_steps": metadata["next_steps"],
        "open_questions": metadata["open_questions"],
        "verification_state": [metadata["verification_state"]] if metadata["verification_state"] else [],
        "files_touched": metadata["files_touched"],
        "tests_run": metadata["tests_run"],
        "implemented_by": metadata["implemented_by"],
        "blocked_by": metadata["blocked_by"],
    }
    for field_name, values in field_map.items():
        hits = sum(1 for token in question_tokens for value in values if token in tokenize(value, drop_generic=False))
        if hits:
            score += hits
            reasons.append(f"{field_name} hits={hits}")

    return score, metadata, reasons


def article_recency_bonus(frontmatter: dict) -> tuple[int, list[str]]:
    """Return ranking bonuses/penalties from canonical decision metadata."""
    score = 0
    reasons: list[str] = []
    superseded_by = metadata_list(frontmatter, "superseded_by")
    current_status = str(frontmatter.get("current_status") or "").lower()

    if superseded_by:
        score -= 12
        reasons.append(f"superseded penalty={len(superseded_by)}")
    elif frontmatter.get("decision_id"):
        score += 4
        reasons.append("canonical decision boost=4")

    if any(term in current_status for term in ("implemented", "active", "complete", "live", "launched")):
        score += 3
        reasons.append("status boost=3")
    elif any(term in current_status for term in ("blocked", "pending", "stalled", "planned")):
        score += 1
        reasons.append("status hint=1")

    return score, reasons


def score_article_content(question_tokens: list[str], path: Path) -> ArticleSignals:
    """Open the article and score the actual content."""
    frontmatter, body = read_markdown_article(path)
    summary = str(frontmatter.get("summary") or "")
    combined = " ".join([summary, body])
    counts = Counter(tokenize(combined))
    score = sum(counts[token] for token in question_tokens)
    sections = parse_article_sections(body)
    metadata_score, metadata, metadata_reasons = score_metadata_fields(question_tokens, frontmatter)
    score += metadata_score
    recency_score, recency_reasons = article_recency_bonus(frontmatter)
    score += recency_score

    snippet_candidates: list[tuple[int, str]] = []
    excerpt_candidates: list[tuple[int, int, str]] = []
    excerpt_sections = ("evidence", "validation", "decision", "decisions", "rationale / evidence")
    for section_name in excerpt_sections:
        for line in sections.get(section_name, []):
            line_score = score_section_line(question_tokens, line, section=section_name)
            if line_score:
                snippet_candidates.append((line_score, line))
            section_rank = excerpt_section_rank(section_name)
            if section_rank:
                excerpt_candidates.append((section_rank, line_score, line))

    if not snippet_candidates:
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

    supporting_excerpts: list[str] = []
    if excerpt_candidates:
        excerpt_candidates.sort(key=lambda item: (-item[0], -item[1], len(item[2])))
        supporting_excerpts = [trim_sentence(text, 220) for _, _, text in excerpt_candidates[:2]]
    else:
        fallback_evidence = []
        for section_name in excerpt_sections:
            fallback_evidence.extend(sections.get(section_name, []))
        supporting_excerpts = [trim_sentence(text, 220) for text in fallback_evidence[:2]]

    if snippet_candidates:
        snippet_candidates.sort(key=lambda item: (-item[0], len(item[1])))
        snippet = snippet_candidates[0][1]
        if sections.get("decision"):
            snippet = sections["decision"][0]
        elif supporting_excerpts:
            snippet = supporting_excerpts[0]
        return ArticleSignals(
            content_score=score,
            snippet=trim_sentence(snippet, 180),
            supporting_excerpts=supporting_excerpts,
            weak_summary=is_weak_summary(summary),
            has_concrete_evidence=bool(supporting_excerpts),
            metadata=metadata,
            score_reasons=[*metadata_reasons, *recency_reasons],
        )

    if summary:
        return ArticleSignals(
            content_score=score,
            snippet=trim_sentence(summary, 180),
            supporting_excerpts=supporting_excerpts,
            weak_summary=is_weak_summary(summary),
            has_concrete_evidence=bool(supporting_excerpts),
            metadata=metadata,
            score_reasons=[*metadata_reasons, *recency_reasons],
        )

    fallback = trim_sentence(body.strip().splitlines()[0] if body.strip() else "No concise summary available.", 180)
    return ArticleSignals(
        content_score=score,
        snippet=fallback,
        supporting_excerpts=supporting_excerpts,
        weak_summary=True,
        has_concrete_evidence=bool(supporting_excerpts),
        metadata=metadata,
        score_reasons=[*metadata_reasons, *recency_reasons],
    )


def select_articles(question: str, shortlist_limit: int = 8, consult_limit: int = 4) -> list[RankedArticle]:
    """Shortlist from the index, then rerank by actual article content."""
    question_tokens = tokenize(question)
    if is_planning_question(question):
        consult_limit = max(consult_limit, 6)
    shortlist = shortlist_articles(question, limit=shortlist_limit)
    consulted: list[RankedArticle] = []

    for candidate in shortlist:
        signals = score_article_content(question_tokens, candidate.path)
        reasons = [*candidate.reasons, f"content hits={signals.content_score}", *signals.score_reasons]
        consulted.append(
            RankedArticle(
                link=candidate.link,
                path=candidate.path,
                article_type=candidate.article_type,
                summary=signals.snippet,
                keywords=candidate.keywords,
                sources=candidate.sources,
                updated=candidate.updated,
                index_score=candidate.index_score,
                content_score=signals.content_score,
                reasons=reasons,
                supporting_excerpts=signals.supporting_excerpts,
                weak_summary=signals.weak_summary,
                has_concrete_evidence=signals.has_concrete_evidence,
                metadata=signals.metadata,
            )
        )

    consulted.sort(key=lambda article: (-article.total_score, -article.index_score, article.link))
    return consulted[:consult_limit]


def is_temporal_question(question: str) -> bool:
    """Return whether the question asks for current or latest state."""
    lowered = question.lower()
    return any(
        phrase in lowered
        for phrase in ("current", "latest", "today", "now", "recent", "as of")
    )


def confidence_penalties(question: str, articles: list[RankedArticle]) -> list[str]:
    """Return confidence penalties derived from source quality and temporal intent."""
    if not articles:
        return []

    penalties: list[str] = []
    top = articles[0]
    if top.weak_summary:
        penalties.append("weak_top_summary")
    if not top.has_concrete_evidence:
        penalties.append("no_top_evidence")
    if is_temporal_question(question):
        freshest = max((article.updated for article in articles if article.updated), default=top.updated)
        if freshest and top.updated and top.updated < freshest:
            penalties.append("temporal_staleness")
    return penalties


def confidence_label(question: str, articles: list[RankedArticle]) -> str:
    """Return a coarse confidence label based on ranking strength and evidence quality."""
    if not articles:
        return "low"

    top_score = articles[0].total_score
    supporting = sum(1 for article in articles if article.total_score > 0)
    penalties = confidence_penalties(question, articles)
    if top_score >= 12 and supporting >= 2:
        if penalties:
            return "medium"
        return "high"
    if top_score >= 7:
        return "medium"
    return "low"


def collect_plan_items(articles: list[RankedArticle]) -> tuple[list[str], list[str], list[str], list[str]]:
    """Collect status, next-step, question, and decision lines from ranked articles."""
    statuses: list[str] = []
    next_steps: list[str] = []
    open_questions: list[str] = []
    decisions: list[str] = []

    for article in articles:
        current_status = str(article.metadata.get("current_status") or "").strip()
        if current_status:
            statuses.append(f"[[{article.link}]] - {current_status}")
        for item in article.metadata.get("next_steps") or []:
            next_steps.append(f"[[{article.link}]] - {item}")
        for item in article.metadata.get("open_questions") or []:
            open_questions.append(f"[[{article.link}]] - {item}")
        if article.article_type == "decision" and not (article.metadata.get("superseded_by") or []):
            decisions.append(f"[[{article.link}]] - {article.summary}")

    return statuses[:5], next_steps[:6], open_questions[:6], decisions[:5]


def build_plan_answer(
    question: str,
    articles: list[RankedArticle],
    *,
    explain: bool,
    include_evidence: bool = False,
) -> str:
    """Build a planning-oriented answer focused on current status and next actions."""
    confidence = confidence_label(question, articles)
    penalties = confidence_penalties(question, articles)
    statuses, next_steps, open_questions, decisions = collect_plan_items(articles)
    lines = ["## Answer", "", f"Confidence: {confidence}", ""]
    lines.extend(["## Current Goal State", "", *(f"- {item}" for item in statuses or ["- No explicit current status found in the top ranked records."])])
    lines.extend(["", "## Next Steps", "", *(f"- {item}" for item in next_steps or ["- No explicit next steps captured yet."])])
    if open_questions:
        lines.extend(["", "## Open Questions", "", *(f"- {item}" for item in open_questions)])
    if decisions:
        lines.extend(["", "## Canonical Decisions", "", *(f"- {item}" for item in decisions)])
    lines.extend(["", "## Sources Consulted"])
    lines.extend(f"- [[{article.link}]]" for article in articles)

    if include_evidence:
        lines.extend(["", "## Supporting Excerpts", ""])
        for article in articles:
            for excerpt in article.supporting_excerpts[:2]:
                lines.append(f"- [[{article.link}]]: {excerpt}")

    if explain:
        lines.extend(["", "## Retrieval Notes", ""])
        lines.append(f"- Confidence penalties: {', '.join(penalties) if penalties else '(none)'}")
        for article in articles:
            lines.append(
                f"- [[{article.link}]]: total={article.total_score}, index={article.index_score}, content={article.content_score}; {', '.join(article.reasons)}"
            )

    return "\n".join(lines)


def build_answer(
    question: str,
    articles: list[RankedArticle],
    *,
    explain: bool,
    include_evidence: bool = False,
    plan_brief: bool = False,
) -> str:
    """Build a deterministic answer from shortlisted articles."""
    if not articles:
        return (
            "I could not find relevant compiled knowledge for that question. "
            "Compile recent daily logs first with `uv run python scripts/compile.py`."
        )

    if plan_brief or is_planning_question(question):
        return build_plan_answer(question, articles, explain=explain, include_evidence=include_evidence)

    confidence = confidence_label(question, articles)
    penalties = confidence_penalties(question, articles)
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

    if include_evidence:
        lines.extend(["", "## Supporting Excerpts", ""])
        for article in articles:
            if not article.supporting_excerpts:
                continue
            for excerpt in article.supporting_excerpts[:2]:
                lines.append(f"- [[{article.link}]]: {excerpt}")

    if explain:
        lines.extend(["", "## Retrieval Notes", ""])
        lines.append(f"- Confidence penalties: {', '.join(penalties) if penalties else '(none)'}")
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
    confidence = confidence_label(question, articles)
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
    parser.add_argument("--evidence", action="store_true", help="Include supporting excerpts from consulted articles")
    parser.add_argument("--plan-brief", action="store_true", help="Summarize current status, next steps, open questions, and canonical decisions")
    args = parser.parse_args()

    articles = select_articles(args.question)
    answer = build_answer(
        args.question,
        articles,
        explain=args.explain,
        include_evidence=args.evidence,
        plan_brief=args.plan_brief,
    )

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
