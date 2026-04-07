"""Query the knowledge base via deterministic index-guided retrieval.

Usage:
    uv run python scripts/query.py "How should I handle auth redirects?"
    uv run python scripts/query.py "What patterns do I use for API design?" --file-back
"""

from __future__ import annotations

import argparse
import re
from collections import Counter
from pathlib import Path

from config import KNOWLEDGE_DIR, QA_DIR, now_iso
from utils import extract_wikilinks, list_wiki_articles, load_state, read_wiki_index, save_state, slugify

STOPWORDS = {
    "the", "a", "an", "to", "for", "of", "and", "or", "in", "on", "is", "are",
    "do", "i", "my", "me", "with", "what", "how", "should", "use", "you",
}


def tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-zA-Z0-9-]+", text.lower())
    return [t for t in tokens if t not in STOPWORDS and len(t) > 2]


def extract_index_rows() -> dict[str, str]:
    """Map wiki link target -> index summary."""
    summaries: dict[str, str] = {}
    for line in read_wiki_index().splitlines():
        if not line.startswith("| [["):
            continue
        parts = [part.strip() for part in line.split("|")]
        if len(parts) < 4:
            continue
        link_col = parts[1]
        summary_col = parts[2]
        match = re.match(r"^\[\[([^\]]+)\]\]$", link_col)
        if match and summary_col:
            summaries[match.group(1)] = summary_col
    return summaries


def score_article(question_tokens: list[str], content: str, path: Path, index_summary: str = "") -> int:
    words = tokenize(content)
    counts = Counter(words)
    score = sum(counts[t] for t in question_tokens)

    path_tokens = set(tokenize(path.stem.replace("-", " ")))
    score += sum(3 for t in question_tokens if t in path_tokens)

    if index_summary:
        index_words = Counter(tokenize(index_summary))
        score += sum(index_words[t] * 2 for t in question_tokens)

    inbound = len(extract_wikilinks(content))
    score += min(3, inbound // 4)
    return score


def top_articles(question: str, limit: int = 6) -> list[Path]:
    q_tokens = tokenize(question)
    scored: list[tuple[int, Path]] = []
    index_summaries = extract_index_rows()

    for article in list_wiki_articles():
        content = article.read_text(encoding="utf-8")
        rel = article.relative_to(KNOWLEDGE_DIR).as_posix().replace(".md", "")
        score = score_article(q_tokens, content, article, index_summaries.get(rel, ""))

        if question.lower() in content.lower():
            score += 6

        if score > 0:
            scored.append((score, article))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [p for _, p in scored[:limit]]


def summarize_article(path: Path, tokens: list[str]) -> str:
    lines = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    candidates = []

    for ln in lines:
        if ln.startswith("#") or ln.startswith("---"):
            continue
        score = sum(1 for t in tokens if t in ln.lower())
        if score:
            candidates.append((score, ln))

    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]

    for ln in lines:
        if ln.startswith("- "):
            return ln[2:]

    return "No concise summary available from this article."


def build_answer(question: str, articles: list[Path]) -> str:
    q_tokens = tokenize(question)

    if not articles:
        return (
            "I could not find relevant compiled knowledge for that question. "
            "Try compiling newer daily logs first with `uv run python scripts/compile.py`."
        )

    lines = ["## Answer", ""]
    lines.append("Based on the most relevant knowledge articles:")
    lines.append("")

    consulted_links: list[str] = []
    for article in articles:
        rel = article.relative_to(KNOWLEDGE_DIR).as_posix().replace(".md", "")
        consulted_links.append(f"[[{rel}]]")
        summary = summarize_article(article, q_tokens)
        lines.append(f"- [[{rel}]]: {summary}")

    lines.append("")
    lines.append("## Synthesis")
    lines.append("")
    lines.append(
        "The retrieved articles suggest consistent practices around the topics above. "
        "Use the cited pages as canonical references and update them after each new session "
        "so future answers improve."
    )
    lines.append("")
    lines.append("## Sources Consulted")
    lines.extend(f"- {link}" for link in consulted_links)

    return "\n".join(lines)


def file_back_answer(question: str, answer: str, articles: list[Path]) -> Path:
    QA_DIR.mkdir(parents=True, exist_ok=True)
    slug = slugify(question) or "query-answer"
    qa_path = QA_DIR / f"{slug}.md"

    consulted = [a.relative_to(KNOWLEDGE_DIR).as_posix().replace(".md", "") for a in articles]
    consulted_yaml = "\n".join(f"  - \"{item}\"" for item in consulted)
    consulted_md = "\n".join(f"- [[{item}]] - Consulted during deterministic retrieval" for item in consulted)

    content = f"""---
title: "Q: {question}"
question: "{question}"
consulted:
{consulted_yaml if consulted_yaml else '  - "(none)"'}
filed: {now_iso()[:10]}
---

# Q: {question}

{answer}

## Sources Consulted

{consulted_md if consulted_md else '- (none)'}

## Follow-Up Questions

- Which daily logs should be recompiled to improve coverage?
- Does this answer need a connection article?
"""

    qa_path.write_text(content, encoding="utf-8")

    index_path = KNOWLEDGE_DIR / "index.md"
    row = f"| [[qa/{qa_path.stem}]] | Filed answer for: {question[:80]} | query | {now_iso()[:10]} |"
    if index_path.exists():
        index_text = index_path.read_text(encoding="utf-8")
        if row not in index_text:
            index_path.write_text(index_text.rstrip() + "\n" + row + "\n", encoding="utf-8")

    log_path = KNOWLEDGE_DIR / "log.md"
    if log_path.exists():
        with open(log_path, "a", encoding="utf-8") as f:
            consulted_links = ", ".join(f"[[{c}]]" for c in consulted) if consulted else "(none)"
            f.write(f"## [{now_iso()}] query (filed) | {question[:72]}\n")
            f.write(f"- Question: {question}\n")
            f.write(f"- Consulted: {consulted_links}\n")
            f.write(f"- Filed to: [[qa/{qa_path.stem}]]\n\n")

    return qa_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Query the personal knowledge base")
    parser.add_argument("question", help="The question to ask")
    parser.add_argument("--file-back", action="store_true", help="Save answer as knowledge/qa article")
    args = parser.parse_args()

    articles = top_articles(args.question)
    answer = build_answer(args.question, articles)

    print(f"Question: {args.question}")
    print(f"File back: {'yes' if args.file_back else 'no'}")
    print("-" * 60)
    print(answer)

    if args.file_back:
        qa_path = file_back_answer(args.question, answer, articles)
        print("\n" + "-" * 60)
        print(f"Answer filed to {qa_path.relative_to(KNOWLEDGE_DIR.parent)}")

    state = load_state()
    state["query_count"] = state.get("query_count", 0) + 1
    save_state(state)


if __name__ == "__main__":
    main()
