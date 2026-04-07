"""Compile daily conversation logs into structured knowledge articles.

This compiler is deterministic and model-agnostic by default so it works in
Codex app/cloud environments without provider-specific SDK requirements.

Usage:
    uv run python scripts/compile.py
    uv run python scripts/compile.py --all
    uv run python scripts/compile.py --file daily/2026-04-01.md
    uv run python scripts/compile.py --dry-run
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from config import CONCEPTS_DIR, CONNECTIONS_DIR, DAILY_DIR, KNOWLEDGE_DIR, now_iso
from utils import file_hash, list_raw_files, list_wiki_articles, load_state, save_state, slugify

ROOT_DIR = Path(__file__).resolve().parent.parent


@dataclass(slots=True)
class ConceptCandidate:
    slug: str
    title: str
    summary: str
    key_points: list[str]
    details: list[str]
    related: list[str]


def ensure_knowledge_scaffold() -> None:
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    CONCEPTS_DIR.mkdir(parents=True, exist_ok=True)
    CONNECTIONS_DIR.mkdir(parents=True, exist_ok=True)

    index_path = KNOWLEDGE_DIR / "index.md"
    if not index_path.exists():
        index_path.write_text(
            "# Knowledge Base Index\n\n"
            "| Article | Summary | Compiled From | Updated |\n"
            "|---------|---------|---------------|---------|\n",
            encoding="utf-8",
        )

    log_path = KNOWLEDGE_DIR / "log.md"
    if not log_path.exists():
        log_path.write_text("# Build Log\n\n", encoding="utf-8")


def parse_sessions(log_content: str) -> list[tuple[str, str]]:
    """Return list of (session_title, session_body)."""
    pattern = re.compile(r"^###\s+(.+)$", flags=re.MULTILINE)
    matches = list(pattern.finditer(log_content))
    sessions: list[tuple[str, str]] = []
    for i, match in enumerate(matches):
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(log_content)
        title = match.group(1).strip()
        body = log_content[start:end].strip()
        if body:
            sessions.append((title, body))
    return sessions


def section_items(body: str, heading: str) -> list[str]:
    pattern = re.compile(
        rf"\*\*{re.escape(heading)}:\*\*\s*(.*?)"
        r"(?=\n\*\*[A-Za-z ]+:\*\*|\Z)",
        flags=re.DOTALL,
    )
    match = pattern.search(body)
    if not match:
        return []

    raw = match.group(1)
    items: list[str] = []
    for line in raw.splitlines():
        clean = line.strip()
        if not clean:
            continue
        clean = re.sub(r"^-\s*(\[[ xX]\]\s*)?", "", clean)
        if clean:
            items.append(clean)
    return items


def one_line_summary(body: str) -> str:
    context = section_items(body, "Context")
    if context:
        return context[0][:140]

    plain = re.sub(r"\s+", " ", body).strip()
    return plain[:140] if plain else "Compiled knowledge extracted from daily log session."


def build_candidate(session_title: str, session_body: str, all_slugs: list[str]) -> ConceptCandidate:
    base_title = re.sub(r"\(\d{1,2}:\d{2}\)", "", session_title).strip(" -")
    base_title = base_title or "Session Concept"

    slug = slugify(base_title)
    if not slug:
        slug = "session-concept"
    original_slug = slug
    suffix = 2
    while slug in all_slugs:
        slug = f"{original_slug}-{suffix}"
        suffix += 1

    summary = one_line_summary(session_body)
    key_points = section_items(session_body, "Decisions Made") or section_items(session_body, "Key Exchanges")
    lessons = section_items(session_body, "Lessons Learned")
    actions = section_items(session_body, "Action Items")

    details = []
    if lessons:
        details.append(
            "Lessons captured from the session indicate practical constraints, gotchas, "
            "and reusable patterns that should be applied in future implementations."
        )
        details.append(" ".join(lessons[:3]))
    else:
        details.append(
            "This concept was derived from a daily session entry and summarizes recurring "
            "implementation behavior observed during repository work."
        )
        details.append(" ".join((key_points or [summary])[:3]))

    related = [s for s in all_slugs if s != slug][:3]

    synthesized_points = key_points[:5] if key_points else [summary]
    if actions:
        synthesized_points.extend([f"Follow-up: {a}" for a in actions[:2]])
    deduped_points = list(dict.fromkeys(synthesized_points))

    return ConceptCandidate(
        slug=slug,
        title=base_title,
        summary=summary,
        key_points=deduped_points[:5],
        details=details,
        related=related[:3],
    )


def read_frontmatter_dates(content: str) -> tuple[str | None, str | None]:
    created = None
    updated = None
    for line in content.splitlines():
        if line.startswith("created:"):
            created = line.split(":", 1)[1].strip()
        if line.startswith("updated:"):
            updated = line.split(":", 1)[1].strip()
    return created, updated


def merge_sources(existing_content: str, new_source: str) -> list[str]:
    if not existing_content:
        return [new_source]

    sources: list[str] = []
    in_sources = False
    for line in existing_content.splitlines():
        if line.strip().startswith("sources:"):
            in_sources = True
            continue
        if in_sources:
            if line.startswith("  - "):
                sources.append(line.split("-", 1)[1].strip().strip('"'))
            elif line.strip() and not line.startswith(" "):
                break

    if new_source not in sources:
        sources.append(new_source)

    return sources or [new_source]


def write_concept(candidate: ConceptCandidate, source_log: str, date_str: str) -> tuple[Path, bool]:
    concept_path = CONCEPTS_DIR / f"{candidate.slug}.md"
    created = date_str
    existing_content = ""

    if concept_path.exists():
        existing_content = concept_path.read_text(encoding="utf-8")
        existing_created, _ = read_frontmatter_dates(existing_content)
        if existing_created:
            created = existing_created

    sources = merge_sources(existing_content, source_log)

    related_lines = (
        "\n".join(
            f"- [[concepts/{slug}]] - Related through shared implementation context"
            for slug in candidate.related
        )
        if candidate.related
        else "- (none yet)"
    )
    source_lines = "\n".join(f"- [[{src}]] - Compiled from session log evidence" for src in sources)
    points = "\n".join(f"- {point}" for point in candidate.key_points)
    details = "\n\n".join(candidate.details)

    content = f"""---
title: "{candidate.title}"
aliases: [{candidate.slug}]
tags: [memory-compiler, codex-workflow]
sources:
"""
    content += "\n".join(f"  - \"{src}\"" for src in sources)
    content += f"""
created: {created}
updated: {date_str}
---

# {candidate.title}

{candidate.summary}

## Key Points

{points}

## Details

{details}

## Related Concepts

{related_lines}

## Sources

{source_lines}
"""

    concept_path.write_text(content, encoding="utf-8")
    return concept_path, bool(existing_content)


def upsert_index_rows(index_path: Path, rows: list[str]) -> None:
    existing = index_path.read_text(encoding="utf-8") if index_path.exists() else ""
    lines = existing.splitlines()
    header = [
        "# Knowledge Base Index",
        "",
        "| Article | Summary | Compiled From | Updated |",
        "|---------|---------|---------------|---------|",
    ]
    prefix = lines[:4] if len(lines) >= 4 else header
    existing_rows = [ln for ln in lines[4:] if ln.strip().startswith("| [[")]
    new_targets = {row.split("|")[1].strip() for row in rows}
    filtered_rows = [ln for ln in existing_rows if ln.split("|")[1].strip() not in new_targets]
    filtered_rows.extend(rows)
    filtered_rows = sorted(set(filtered_rows), key=str.casefold)
    index_path.write_text("\n".join(prefix + filtered_rows).rstrip() + "\n", encoding="utf-8")


def append_build_log(log_path: Path, log_name: str, created: list[str], updated: list[str]) -> None:
    timestamp = now_iso()
    created_str = ", ".join(created) if created else "(none)"
    updated_str = ", ".join(updated) if updated else "(none)"

    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"## [{timestamp}] compile | {log_name}\n")
        f.write(f"- Source: daily/{log_name}\n")
        f.write(f"- Articles created: {created_str}\n")
        f.write(f"- Articles updated: {updated_str}\n\n")


def compile_daily_log(log_path: Path, state: dict) -> tuple[int, int]:
    ensure_knowledge_scaffold()
    log_content = log_path.read_text(encoding="utf-8")
    sessions = parse_sessions(log_content)

    if not sessions:
        return 0, 0

    existing_slugs = [p.stem for p in list_wiki_articles() if p.parent == CONCEPTS_DIR]
    index_rows: list[str] = []
    created_links: list[str] = []
    updated_links: list[str] = []

    today = now_iso()[:10]
    source_log = f"daily/{log_path.name}"

    for session_title, session_body in sessions:
        candidate = build_candidate(session_title, session_body, existing_slugs)
        concept_path, was_update = write_concept(candidate, source_log, today)
        existing_slugs.append(candidate.slug)

        link = f"[[concepts/{concept_path.stem}]]"
        row = f"| {link} | {candidate.summary} | {source_log} | {today} |"
        index_rows.append(row)
        if was_update:
            updated_links.append(link)
        else:
            created_links.append(link)

    upsert_index_rows(KNOWLEDGE_DIR / "index.md", index_rows)
    append_build_log(KNOWLEDGE_DIR / "log.md", log_path.name, created_links, updated_links)

    state.setdefault("ingested", {})[log_path.name] = {
        "hash": file_hash(log_path),
        "compiled_at": now_iso(),
        "cost_usd": 0.0,
    }
    save_state(state)

    return len(created_links), len(updated_links)


def main() -> None:
    parser = argparse.ArgumentParser(description="Compile daily logs into knowledge articles")
    parser.add_argument("--all", action="store_true", help="Force recompile all logs")
    parser.add_argument("--file", type=str, help="Compile a specific daily log file")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be compiled")
    args = parser.parse_args()

    state = load_state()

    if args.file:
        target = Path(args.file)
        if not target.is_absolute():
            target = DAILY_DIR / target.name
        if not target.exists():
            target = ROOT_DIR / args.file
        if not target.exists():
            print(f"Error: {args.file} not found")
            sys.exit(1)
        to_compile = [target]
    else:
        all_logs = list_raw_files()
        if args.all:
            to_compile = all_logs
        else:
            to_compile = []
            for log_path in all_logs:
                prev = state.get("ingested", {}).get(log_path.name, {})
                if not prev or prev.get("hash") != file_hash(log_path):
                    to_compile.append(log_path)

    if not to_compile:
        print("Nothing to compile - all daily logs are up to date.")
        return

    print(f"{'[DRY RUN] ' if args.dry_run else ''}Files to compile ({len(to_compile)}):")
    for f in to_compile:
        print(f"  - {f.name}")

    if args.dry_run:
        return

    total_created = 0
    total_updated = 0
    for idx, log_path in enumerate(to_compile, 1):
        print(f"\n[{idx}/{len(to_compile)}] Compiling {log_path.name}...")
        created, updated = compile_daily_log(log_path, state)
        total_created += created
        total_updated += updated
        print(f"  Created: {created}, Updated: {updated}")

    articles = list_wiki_articles()
    print("\nCompilation complete.")
    print(f"Knowledge base: {len(articles)} articles")
    print(f"This run: {total_created} created, {total_updated} updated")


if __name__ == "__main__":
    main()
