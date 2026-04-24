"""Lint the knowledge base for structural and maintenance health."""

from __future__ import annotations

import argparse
from collections import defaultdict
from itertools import combinations
from pathlib import Path

from config import CONCEPTS_DIR, CONNECTIONS_DIR, DASHBOARDS_DIR, DECISIONS_DIR, GOALS_DIR, INDEX_FILE, KNOWLEDGE_DIR, REPORTS_DIR, now_iso, today_iso
from utils import (
    build_index_entry,
    canonical_concept_id,
    count_inbound_links,
    extract_wikilinks,
    file_hash,
    get_article_word_count,
    index_snapshot,
    is_weak_summary,
    list_raw_files,
    list_wiki_articles,
    load_state,
    parse_daily_sessions,
    parse_article_sections,
    polarity_subject,
    read_markdown_article,
    rebuild_index,
    render_index_lines,
    save_state,
    wiki_article_exists,
    write_markdown_article,
)


def issue(severity: str, check: str, file: str, detail: str, *, auto_fixable: bool = False) -> dict:
    """Build a lint issue record."""
    item = {"severity": severity, "check": check, "file": file, "detail": detail}
    if auto_fixable:
        item["auto_fixable"] = True
    return item


def check_broken_links() -> list[dict]:
    issues = []
    for article in list_wiki_articles():
        content = article.read_text(encoding="utf-8")
        rel = article.relative_to(KNOWLEDGE_DIR).as_posix()
        for link in extract_wikilinks(content):
            if link.startswith("daily/"):
                continue
            if not wiki_article_exists(link):
                issues.append(issue("error", "broken_link", rel, f"Broken link: [[{link}]] - target does not exist"))
    return issues


def check_orphan_pages() -> list[dict]:
    issues = []
    for article in list_wiki_articles():
        if article.parent == DASHBOARDS_DIR:
            continue
        rel = article.relative_to(KNOWLEDGE_DIR).as_posix()
        link_target = rel.replace(".md", "")
        if count_inbound_links(link_target) == 0:
            issues.append(issue("warning", "orphan_page", rel, f"Orphan page: no other articles link to [[{link_target}]]"))
    return issues


def check_orphan_sources() -> list[dict]:
    state = load_state()
    ingested = state.get("ingested", {})
    issues = []
    for log_path in list_raw_files():
        if log_path.name not in ingested:
            issues.append(
                issue(
                    "warning",
                    "orphan_source",
                    f"daily/{log_path.name}",
                    f"Uncompiled daily log: {log_path.name} has not been ingested",
                )
            )
    return issues


def check_stale_articles() -> list[dict]:
    state = load_state()
    ingested = state.get("ingested", {})
    issues = []
    for log_path in list_raw_files():
        if log_path.name in ingested and ingested[log_path.name].get("hash") != file_hash(log_path):
            issues.append(
                issue(
                    "warning",
                    "stale_article",
                    f"daily/{log_path.name}",
                    f"Stale: {log_path.name} has changed since the last compile",
                )
            )
    return issues


def check_missing_backlinks() -> list[dict]:
    issues = []
    for article in list_wiki_articles():
        if article.parent == DASHBOARDS_DIR:
            continue
        content = article.read_text(encoding="utf-8")
        rel = article.relative_to(KNOWLEDGE_DIR).as_posix()
        source_link = rel.replace(".md", "")

        for link in extract_wikilinks(content):
            if link.startswith("daily/") or not wiki_article_exists(link):
                continue
            target_path = KNOWLEDGE_DIR / f"{link}.md"
            target_content = target_path.read_text(encoding="utf-8")
            if f"[[{source_link}]]" not in target_content:
                issues.append(
                    issue(
                        "suggestion",
                        "missing_backlink",
                        rel,
                        f"[[{source_link}]] links to [[{link}]] but not vice versa",
                        auto_fixable=True,
                    )
                )
    return issues


def check_duplicate_concepts() -> list[dict]:
    issues = []
    concept_map: dict[str, list[str]] = defaultdict(list)
    for article in CONCEPTS_DIR.glob("*.md"):
        frontmatter, body = read_markdown_article(article)
        title = str(frontmatter.get("title") or article.stem)
        keywords = " ".join(frontmatter.get("keywords") or [])
        canonical = canonical_concept_id(title, str(frontmatter.get("summary") or ""), keywords, body[:200])
        concept_map[canonical].append(article.relative_to(KNOWLEDGE_DIR).as_posix())

    for canonical, paths in concept_map.items():
        if len(paths) > 1:
            for path in paths:
                issues.append(
                    issue(
                        "warning",
                        "duplicate_concept",
                        path,
                        f"Possible duplicate concept cluster `{canonical}` across: {', '.join(paths)}",
                    )
                )
    return issues


def check_weak_summaries() -> list[dict]:
    issues = []
    for article in list_wiki_articles():
        frontmatter, _ = read_markdown_article(article)
        summary = str(frontmatter.get("summary") or "").strip()
        if is_weak_summary(summary):
            issues.append(
                issue(
                    "suggestion",
                    "weak_summary",
                    article.relative_to(KNOWLEDGE_DIR).as_posix(),
                    "Summary is missing or too weak to support reliable retrieval",
                )
            )
    return issues


def check_thin_codex_summaries() -> list[dict]:
    issues = []
    for log_path in list_raw_files():
        for session in parse_daily_sessions(log_path):
            if session.source_type != "codex-summary":
                continue
            if session.decisions or session.tests_run or session.blockers or session.actions or session.evidence_excerpts:
                continue
            issues.append(
                issue(
                    "suggestion",
                    "thin_codex_summary",
                    f"daily/{log_path.name}",
                    f"Session `{session.session_id}` has only generic context and no explicit decisions, validation, blockers, evidence, or next steps",
                )
            )
    return issues


def check_missing_provenance() -> list[dict]:
    issues = []
    for article in list_wiki_articles():
        frontmatter, _ = read_markdown_article(article)
        if article.parent not in {DASHBOARDS_DIR, GOALS_DIR, DECISIONS_DIR, CONCEPTS_DIR, CONNECTIONS_DIR}:
            continue
        if not frontmatter.get("source_sessions") or not frontmatter.get("source_logs"):
            issues.append(
                issue(
                    "warning",
                    "missing_provenance",
                    article.relative_to(KNOWLEDGE_DIR).as_posix(),
                    "Managed dashboard/goal/decision/concept/connection article is missing source_sessions or source_logs",
                )
            )
    return issues


def check_stale_index_rows() -> list[dict]:
    current = index_snapshot()
    expected = [line for line in render_index_lines() if line.startswith("| [[")]
    if current == expected:
        return []
    return [
        issue(
            "warning",
            "stale_index",
            "knowledge/index.md",
            "Index rows do not match the current knowledge articles",
            auto_fixable=True,
        )
    ]


def check_empty_connections() -> list[dict]:
    issues = []
    for article in CONNECTIONS_DIR.glob("*.md"):
        frontmatter, body = read_markdown_article(article)
        if not frontmatter.get("source_sessions") or str(frontmatter.get("cooccurrence_count") or "0") in {"0", ""}:
            issues.append(
                issue(
                    "warning",
                    "empty_connection",
                    article.relative_to(KNOWLEDGE_DIR).as_posix(),
                    "Connection article has no source sessions or zero cooccurrence count",
                )
            )
        if get_article_word_count(article) < 40:
            issues.append(
                issue(
                    "suggestion",
                    "thin_connection",
                    article.relative_to(KNOWLEDGE_DIR).as_posix(),
                    "Connection article is unusually thin",
                )
            )
    return issues


def check_possible_conflicts() -> list[dict]:
    issues = []
    concept_records = []
    for article in CONCEPTS_DIR.glob("*.md"):
        frontmatter, body = read_markdown_article(article)
        sections = parse_article_sections(body)
        decisions = sections.get("decisions", [])
        keywords = set(frontmatter.get("keywords") or [])
        concept_records.append(
            {
                "path": article.relative_to(KNOWLEDGE_DIR).as_posix(),
                "keywords": keywords,
                "decisions": decisions,
            }
        )

    for left, right in combinations(concept_records, 2):
        if len(left["keywords"] & right["keywords"]) == 0:
            continue
        for left_decision in left["decisions"]:
            left_polarity, left_subject = polarity_subject(left_decision)
            if not left_polarity or len(left_subject) < 2:
                continue
            for right_decision in right["decisions"]:
                right_polarity, right_subject = polarity_subject(right_decision)
                if not right_polarity or left_polarity == right_polarity:
                    continue
                if len(set(left_subject) & set(right_subject)) >= 2:
                    issues.append(
                        issue(
                            "suggestion",
                            "possible_conflict",
                            left["path"],
                            f"Possible conflict with {right['path']}: `{left_decision}` vs `{right_decision}`",
                        )
                    )
                    break
    return issues


def apply_missing_backlink_fix(issue_item: dict) -> bool:
    """Insert a backlink into the target article when safe."""
    match = None
    detail = issue_item["detail"]
    if detail.startswith("[[") and " links to [[" in detail:
        source_link, target_link = detail.split(" links to ")
        source_link = source_link[2:-2]
        target_link = target_link[2 : target_link.index("]]")]
        match = (source_link, target_link)
    if not match:
        return False

    source_link, target_link = match
    target_path = KNOWLEDGE_DIR / f"{target_link}.md"
    if not target_path.exists():
        return False

    frontmatter, body = read_markdown_article(target_path)
    if f"[[{source_link}]]" in body:
        return False

    backlink_line = f"- [[{source_link}]] - Added by lint autofix"
    if "## Related Concepts" in body:
        insertion_point = body.find("\n## ", body.find("## Related Concepts") + 1)
        if insertion_point == -1:
            body = body.rstrip() + "\n" + backlink_line + "\n"
        else:
            prefix = body[:insertion_point].rstrip()
            suffix = body[insertion_point:]
            body = prefix + "\n" + backlink_line + "\n\n" + suffix.lstrip("\n")
    else:
        body = body.rstrip() + f"\n\n## Related Concepts\n{backlink_line}\n"

    write_markdown_article(target_path, frontmatter, body)
    return True


def apply_autofixes(issues: list[dict]) -> int:
    """Apply safe autofixes and return the number of changes made."""
    fixed = 0
    index_fixed = False
    for issue_item in issues:
        if not issue_item.get("auto_fixable"):
            continue
        if issue_item["check"] == "missing_backlink" and apply_missing_backlink_fix(issue_item):
            fixed += 1
        elif issue_item["check"] == "stale_index" and not index_fixed:
            rebuild_index()
            fixed += 1
            index_fixed = True
    return fixed


def run_checks(structural_only: bool) -> list[dict]:
    """Run the configured lint checks."""
    checks = [
        check_broken_links,
        check_orphan_pages,
        check_orphan_sources,
        check_stale_articles,
        check_missing_backlinks,
        check_duplicate_concepts,
        check_weak_summaries,
        check_thin_codex_summaries,
        check_missing_provenance,
        check_stale_index_rows,
        check_empty_connections,
    ]
    issues: list[dict] = []
    for fn in checks:
        issues.extend(fn())
    if not structural_only:
        issues.extend(check_possible_conflicts())
    return issues


def generate_report(all_issues: list[dict], *, fixed_count: int) -> str:
    errors = [item for item in all_issues if item["severity"] == "error"]
    warnings = [item for item in all_issues if item["severity"] == "warning"]
    suggestions = [item for item in all_issues if item["severity"] == "suggestion"]

    lines = [
        f"# Lint Report - {today_iso()}",
        "",
        f"**Total issues:** {len(all_issues)}",
        f"- Errors: {len(errors)}",
        f"- Warnings: {len(warnings)}",
        f"- Suggestions: {len(suggestions)}",
        f"- Autofixes applied: {fixed_count}",
        "",
    ]

    for severity, issues, marker in [
        ("Errors", errors, "x"),
        ("Warnings", warnings, "!"),
        ("Suggestions", suggestions, "?"),
    ]:
        if not issues:
            continue
        lines.append(f"## {severity}")
        lines.append("")
        for item in issues:
            suffix = " (auto-fixable)" if item.get("auto_fixable") else ""
            lines.append(f"- **[{marker}]** `{item['file']}` - {item['detail']}{suffix}")
        lines.append("")

    if not all_issues:
        lines.append("All checks passed. Knowledge base is healthy.")
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Lint the knowledge base")
    parser.add_argument(
        "--structural-only",
        action="store_true",
        help="Skip conflict heuristics and run structural checks only",
    )
    parser.add_argument(
        "--autofix",
        action="store_true",
        help="Apply safe fixes for stale index rows and missing backlinks",
    )
    args = parser.parse_args()

    print("Running knowledge base lint checks...")
    issues = run_checks(args.structural_only)
    fixed_count = apply_autofixes(issues) if args.autofix else 0
    if fixed_count:
        issues = run_checks(args.structural_only)

    report = generate_report(issues, fixed_count=fixed_count)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"lint-{today_iso()}.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"Report saved to: {report_path}")

    state = load_state()
    state["last_lint"] = now_iso()
    save_state(state)

    errors = sum(1 for item in issues if item["severity"] == "error")
    warnings = sum(1 for item in issues if item["severity"] == "warning")
    suggestions = sum(1 for item in issues if item["severity"] == "suggestion")
    print(f"Results: {errors} errors, {warnings} warnings, {suggestions} suggestions")
    if fixed_count:
        print(f"Autofixes applied: {fixed_count}")

    if errors > 0:
        print("Errors found - knowledge base needs attention.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
