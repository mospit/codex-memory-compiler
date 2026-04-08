"""Compile daily conversation logs into structured knowledge articles."""

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path

from config import CONCEPTS_DIR, CONNECTIONS_DIR, DAILY_DIR, LOG_FILE, now_iso, today_iso
from utils import (
    MANAGED_BY,
    canonical_concept_id,
    ensure_knowledge_scaffold,
    extract_keywords,
    extract_wikilinks,
    file_hash,
    humanize_slug,
    list_raw_files,
    list_wiki_articles,
    load_state,
    managed_article_paths,
    parse_daily_sessions,
    rebuild_index,
    remove_stale_managed_articles,
    save_state,
    slugify,
    tokenize,
    trim_sentence,
    unique_preserve_order,
    write_markdown_article,
)

ROOT_DIR = Path(__file__).resolve().parent.parent
CONNECTION_THRESHOLD = 2


@dataclass(slots=True)
class SessionRecord:
    """Per-session compile metadata."""

    session_id: str
    article_source: str
    title: str
    source_type: str
    context: str
    keywords: list[str]
    full_text: str


@dataclass(slots=True)
class CompiledSession:
    """Session paired with its primary concept id."""

    primary_concept_id: str
    session: object


@dataclass(slots=True)
class ConceptAggregate:
    """Aggregated concept material across sessions."""

    concept_id: str
    aliases: list[str] = field(default_factory=list)
    alias_slugs: set[str] = field(default_factory=set)
    keywords: Counter[str] = field(default_factory=Counter)
    source_sessions: list[str] = field(default_factory=list)
    source_logs: list[str] = field(default_factory=list)
    source_types: Counter[str] = field(default_factory=Counter)
    workspaces: list[str] = field(default_factory=list)
    repos: list[str] = field(default_factory=list)
    task_refs: list[str] = field(default_factory=list)
    contexts: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    lessons: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    sessions: list[SessionRecord] = field(default_factory=list)
    related_counts: Counter[str] = field(default_factory=Counter)


def resolve_logs(args: argparse.Namespace, state: dict) -> tuple[list[Path], list[Path]]:
    """Return selected logs and the full corpus used to rebuild knowledge."""
    all_logs = list_raw_files()
    if args.file:
        target = Path(args.file)
        if not target.is_absolute():
            target = DAILY_DIR / target.name
        if not target.exists():
            target = ROOT_DIR / args.file
        if not target.exists():
            print(f"Error: {args.file} not found")
            raise SystemExit(1)
        return [target], all_logs or [target]

    if args.all:
        return all_logs, all_logs

    changed: list[Path] = []
    for log_path in all_logs:
        previous = state.get("ingested", {}).get(log_path.name, {})
        if previous.get("hash") != file_hash(log_path):
            changed.append(log_path)
    return changed, all_logs


def candidate_aliases(session, concept_id: str) -> set[str]:
    """Build deterministic aliases used during concept matching."""
    aliases = {concept_id, slugify(session.title)}
    if session.task_ref:
        aliases.add(slugify(session.task_ref))
    if len(session.keywords) >= 2:
        aliases.add("-".join(session.keywords[:2]))
    return {alias for alias in aliases if alias}


def locate_concept_id(
    alias_index: dict[str, str],
    concept_id: str,
    aliases: set[str],
) -> str | None:
    """Find an existing concept match by canonical id or alias."""
    if concept_id in alias_index:
        return alias_index[concept_id]
    for alias in aliases:
        if alias in alias_index:
            return alias_index[alias]
    return None


def register_session(aggregates: dict[str, ConceptAggregate], session) -> str:
    """Merge a parsed daily session into a concept aggregate."""
    concept_id = canonical_concept_id(session.title, session.context, *session.decisions, *session.lessons)
    alias_index: dict[str, str] = {}
    for existing in aggregates.values():
        for alias in existing.alias_slugs | {existing.concept_id}:
            alias_index[alias] = existing.concept_id

    aliases = candidate_aliases(session, concept_id)
    concept_key = locate_concept_id(alias_index, concept_id, aliases) or concept_id

    aggregate = aggregates.setdefault(concept_key, ConceptAggregate(concept_id=concept_key))
    aggregate.aliases = unique_preserve_order([*aggregate.aliases, session.title])
    aggregate.alias_slugs.update(aliases)
    aggregate.keywords.update(session.keywords)
    aggregate.source_sessions = unique_preserve_order([*aggregate.source_sessions, session.session_id])
    aggregate.source_logs = unique_preserve_order([*aggregate.source_logs, session.article_source])
    aggregate.source_types.update([session.source_type])
    aggregate.contexts = unique_preserve_order([*aggregate.contexts, session.context])
    aggregate.decisions = unique_preserve_order([*aggregate.decisions, *session.decisions])
    aggregate.lessons = unique_preserve_order([*aggregate.lessons, *session.lessons])
    aggregate.actions = unique_preserve_order([*aggregate.actions, *session.actions])
    aggregate.workspaces = unique_preserve_order(
        [*aggregate.workspaces, *([session.workspace] if session.workspace else [])]
    )
    aggregate.repos = unique_preserve_order([*aggregate.repos, *([session.repo] if session.repo else [])])
    aggregate.task_refs = unique_preserve_order(
        [*aggregate.task_refs, *([session.task_ref] if session.task_ref else [])]
    )

    evidence = f"[[{session.article_source}]] / `{session.session_id}` ({session.source_type}): {session.context}"
    aggregate.evidence = unique_preserve_order([*aggregate.evidence, trim_sentence(evidence, 220)])
    aggregate.sessions.append(
        SessionRecord(
            session_id=session.session_id,
            article_source=session.article_source,
            title=session.title,
            source_type=session.source_type,
            context=session.context,
            keywords=session.keywords,
            full_text=session.full_text,
        )
    )
    return concept_key


def mention_score(session, aggregate: ConceptAggregate, primary_concept_id: str) -> int:
    """Score whether a concept is explicitly mentioned in a session."""
    if aggregate.concept_id == primary_concept_id:
        return 999

    score = 0
    normalized_tokens = set(tokenize(session.full_text))
    concept_tokens = [token for token in aggregate.concept_id.split("-") if token]
    overlap = sum(1 for token in concept_tokens if token in normalized_tokens)
    if overlap >= max(2, len(concept_tokens) - 1):
        score += 4 + overlap

    raw_lower = session.full_text.lower()
    for alias in aggregate.aliases:
        alias_lower = alias.lower()
        if len(alias_lower) >= 6 and alias_lower in raw_lower:
            score = max(score, 7)

    for alias_slug in aggregate.alias_slugs:
        alias_tokens = alias_slug.split("-")
        if len(alias_tokens) >= 2 and all(token in normalized_tokens for token in alias_tokens):
            score = max(score, 5 + len(alias_tokens))

    for wikilink in extract_wikilinks(session.raw_body):
        if wikilink == f"concepts/{aggregate.concept_id}":
            score = max(score, 10)

    return score


def build_session_mentions(
    aggregates: dict[str, ConceptAggregate],
    session_lookup: dict[str, CompiledSession],
) -> dict[str, list[str]]:
    """Return concept ids mentioned in each session."""
    mentions: dict[str, list[str]] = {}
    for session_id, compiled in session_lookup.items():
        session = compiled.session
        primary_id = compiled.primary_concept_id
        scored: list[tuple[int, str]] = []
        for aggregate in aggregates.values():
            score = mention_score(session, aggregate, primary_id)
            if aggregate.concept_id == primary_id or score >= 5:
                scored.append((score, aggregate.concept_id))

        scored.sort(key=lambda item: (-item[0], item[1]))
        concept_ids = unique_preserve_order([concept_id for _, concept_id in scored][:4])
        mentions[session_id] = concept_ids
    return mentions


def build_related_counts(aggregates: dict[str, ConceptAggregate], session_mentions: dict[str, list[str]]) -> dict[tuple[str, str], list[str]]:
    """Compute pairwise concept co-occurrence across sessions."""
    pair_sessions: dict[tuple[str, str], list[str]] = defaultdict(list)
    for session_id, concept_ids in session_mentions.items():
        for left, right in combinations(sorted(set(concept_ids)), 2):
            pair_sessions[(left, right)].append(session_id)
            aggregates[left].related_counts[right] += 1
            aggregates[right].related_counts[left] += 1

    return pair_sessions


def choose_summary(aggregate: ConceptAggregate) -> str:
    """Pick a stable concept summary."""
    if aggregate.contexts:
        return trim_sentence(aggregate.contexts[0], 160)
    if aggregate.decisions:
        return trim_sentence(aggregate.decisions[0], 160)
    if aggregate.lessons:
        return trim_sentence(aggregate.lessons[0], 160)
    return f"Compiled concept for {humanize_slug(aggregate.concept_id)}."


def concept_keywords(aggregate: ConceptAggregate) -> list[str]:
    """Return stable keywords for a concept aggregate."""
    if aggregate.keywords:
        ranked = sorted(aggregate.keywords, key=lambda token: (-aggregate.keywords[token], token))
        return ranked[:6]
    return extract_keywords((humanize_slug(aggregate.concept_id), 4), limit=4)


def concept_created_date(aggregate: ConceptAggregate) -> str:
    """Return the first source log date for a concept."""
    dates = []
    for source in aggregate.source_logs:
        stem = Path(source).stem
        if len(stem) == 10 and stem[4] == "-" and stem[7] == "-":
            dates.append(stem)
    return min(dates) if dates else today_iso()


def write_concept_articles(
    aggregates: dict[str, ConceptAggregate],
    pair_sessions: dict[tuple[str, str], list[str]],
) -> tuple[list[str], list[str]]:
    """Write deterministic concept pages and return created/updated links."""
    existing = managed_article_paths(CONCEPTS_DIR)
    desired_stems: set[str] = set()
    created_links: list[str] = []
    updated_links: list[str] = []

    for concept_id in sorted(aggregates):
        aggregate = aggregates[concept_id]
        desired_stems.add(concept_id)
        path = CONCEPTS_DIR / f"{concept_id}.md"
        created = concept_created_date(aggregate)
        updated = today_iso()
        title = humanize_slug(concept_id)
        summary = choose_summary(aggregate)
        keywords = concept_keywords(aggregate)

        related_lines: list[str] = []
        for related_id, count in aggregate.related_counts.most_common(5):
            connection_id = "__".join(sorted([concept_id, related_id]))
            if (min(concept_id, related_id), max(concept_id, related_id)) in pair_sessions and count >= CONNECTION_THRESHOLD:
                related_lines.append(
                    f"- [[concepts/{related_id}]] - Co-occurred in {count} session(s); see [[connections/{connection_id}]]"
                )
            else:
                related_lines.append(
                    f"- [[concepts/{related_id}]] - Mentioned alongside this concept in {count} session(s)"
                )

        source_lines = [
            f"- [[{source}]] - Sessions: {', '.join(f'`{record.session_id}`' for record in aggregate.sessions if record.article_source == source)}"
            for source in aggregate.source_logs
        ]
        body_sections = [
            f"# {title}",
            "",
            summary,
            "",
            "## Decisions",
            *(f"- {item}" for item in aggregate.decisions or ["No explicit decisions captured yet."]),
            "",
            "## Lessons",
            *(f"- {item}" for item in aggregate.lessons or ["No explicit lessons captured yet."]),
            "",
            "## Follow-Ups",
            *(f"- [ ] {item}" for item in aggregate.actions or ["No follow-up actions captured yet."]),
            "",
            "## Evidence",
            *(f"- {item}" for item in aggregate.evidence[:8]),
            "",
            "## Related Concepts",
            *(related_lines or ["- None yet."]),
            "",
            "## Sources",
            *(source_lines or ["- None yet."]),
        ]

        frontmatter = {
            "managed_by": MANAGED_BY,
            "schema_version": "2",
            "title": title,
            "concept_id": concept_id,
            "aliases": aggregate.aliases,
            "keywords": keywords,
            "summary": summary,
            "source_sessions": aggregate.source_sessions,
            "source_logs": aggregate.source_logs,
            "source_types": sorted(aggregate.source_types),
            "workspaces": aggregate.workspaces,
            "repos": aggregate.repos,
            "task_refs": aggregate.task_refs,
            "created": created,
            "updated": updated,
        }
        write_markdown_article(path, frontmatter, "\n".join(body_sections))

        link = f"[[concepts/{concept_id}]]"
        if concept_id in existing:
            updated_links.append(link)
        else:
            created_links.append(link)

    remove_stale_managed_articles(CONCEPTS_DIR, desired_stems)
    return created_links, updated_links


def write_connection_articles(
    aggregates: dict[str, ConceptAggregate],
    pair_sessions: dict[tuple[str, str], list[str]],
    session_lookup: dict[str, CompiledSession],
) -> tuple[list[str], list[str]]:
    """Write connection pages generated from repeated concept co-occurrence."""
    existing = managed_article_paths(CONNECTIONS_DIR)
    desired_stems: set[str] = set()
    created_links: list[str] = []
    updated_links: list[str] = []

    for pair, session_ids in sorted(pair_sessions.items()):
        if len(session_ids) < CONNECTION_THRESHOLD:
            continue

        left, right = pair
        connection_id = "__".join(pair)
        desired_stems.add(connection_id)
        path = CONNECTIONS_DIR / f"{connection_id}.md"
        left_title = humanize_slug(left)
        right_title = humanize_slug(right)
        title = f"{left_title} and {right_title}"
        summary = f"{left_title} and {right_title} co-occurred in {len(session_ids)} session(s)."
        source_logs = unique_preserve_order(
            [session_lookup[session_id].session.article_source for session_id in session_ids]
        )
        source_sessions = unique_preserve_order(session_ids)
        keywords = unique_preserve_order([*concept_keywords(aggregates[left]), *concept_keywords(aggregates[right])])[:6]

        evidence_lines = []
        for session_id in session_ids:
            session = session_lookup[session_id].session
            evidence_lines.append(
                f"- [[{session.article_source}]] / `{session.session_id}`: {trim_sentence(session.context, 180)}"
            )

        body_sections = [
            f"# {title}",
            "",
            summary,
            "",
            "## Relationship",
            f"- [[concepts/{left}]]",
            f"- [[concepts/{right}]]",
            "",
            "## Evidence",
            *evidence_lines,
            "",
            "## Sources",
            *(f"- [[{source}]]" for source in source_logs),
        ]

        frontmatter = {
            "managed_by": MANAGED_BY,
            "schema_version": "2",
            "title": title,
            "connection_id": connection_id,
            "concepts": [f"concepts/{left}", f"concepts/{right}"],
            "keywords": keywords,
            "summary": summary,
            "source_sessions": source_sessions,
            "source_logs": source_logs,
            "cooccurrence_count": str(len(session_ids)),
            "created": min(Path(source).stem for source in source_logs),
            "updated": today_iso(),
        }
        write_markdown_article(path, frontmatter, "\n".join(body_sections))

        link = f"[[connections/{connection_id}]]"
        if connection_id in existing:
            updated_links.append(link)
        else:
            created_links.append(link)

    remove_stale_managed_articles(CONNECTIONS_DIR, desired_stems)
    return created_links, updated_links


def append_build_log(
    selected_logs: list[Path],
    created_links: list[str],
    updated_links: list[str],
    total_sessions: int,
) -> None:
    """Append a compile summary to the build log."""
    sources = ", ".join(f"daily/{path.name}" for path in selected_logs) if selected_logs else "(none)"
    created_text = ", ".join(created_links) if created_links else "(none)"
    updated_text = ", ".join(updated_links) if updated_links else "(none)"

    ensure_knowledge_scaffold()
    with open(LOG_FILE, "a", encoding="utf-8") as handle:
        handle.write(f"## [{now_iso()}] compile\n")
        handle.write(f"- Triggered by: {sources}\n")
        handle.write(f"- Sessions compiled: {total_sessions}\n")
        handle.write(f"- Articles created: {created_text}\n")
        handle.write(f"- Articles updated: {updated_text}\n\n")


def compile_corpus(selected_logs: list[Path], all_logs: list[Path], state: dict, *, dry_run: bool) -> tuple[int, int]:
    """Compile the entire daily-log corpus into deterministic knowledge artifacts."""
    ensure_knowledge_scaffold()
    aggregates: dict[str, ConceptAggregate] = {}
    session_lookup: dict[str, CompiledSession] = {}

    for log_path in all_logs:
        for session in parse_daily_sessions(log_path):
            primary_concept_id = register_session(aggregates, session)
            session_lookup[session.session_id] = CompiledSession(
                primary_concept_id=primary_concept_id,
                session=session,
            )

    session_mentions = build_session_mentions(aggregates, session_lookup)
    pair_sessions = build_related_counts(aggregates, session_mentions)

    if dry_run:
        concept_count = len(aggregates)
        connection_count = sum(1 for sessions in pair_sessions.values() if len(sessions) >= CONNECTION_THRESHOLD)
        print(f"[DRY RUN] Concept pages: {concept_count}")
        print(f"[DRY RUN] Connection pages: {connection_count}")
        print(f"[DRY RUN] Sessions parsed: {len(session_lookup)}")
        return concept_count, connection_count

    concept_created, concept_updated = write_concept_articles(aggregates, pair_sessions)
    connection_created, connection_updated = write_connection_articles(aggregates, pair_sessions, session_lookup)
    rebuild_index()

    all_created = concept_created + connection_created
    all_updated = concept_updated + connection_updated
    append_build_log(selected_logs, all_created, all_updated, len(session_lookup))

    state["ingested"] = {
        log_path.name: {
            "hash": file_hash(log_path),
            "compiled_at": now_iso(),
            "cost_usd": 0.0,
        }
        for log_path in all_logs
    }
    save_state(state)

    return len(all_created), len(all_updated)


def main() -> None:
    parser = argparse.ArgumentParser(description="Compile daily logs into knowledge articles")
    parser.add_argument("--all", action="store_true", help="Force recompile all logs")
    parser.add_argument("--file", type=str, help="Compile a specific daily log file")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be compiled")
    args = parser.parse_args()

    state = load_state()
    selected_logs, all_logs = resolve_logs(args, state)
    if not selected_logs:
        print("Nothing to compile - all daily logs are up to date.")
        return

    print(f"{'[DRY RUN] ' if args.dry_run else ''}Selected logs ({len(selected_logs)}):")
    for log_path in selected_logs:
        print(f"  - {log_path.name}")
    if args.file and len(all_logs) > 1:
        print("Rebuilding knowledge using the full daily-log corpus because concept merging is corpus-wide.")

    created, updated = compile_corpus(selected_logs, all_logs, state, dry_run=args.dry_run)
    if args.dry_run:
        return

    articles = list_wiki_articles()
    print("\nCompilation complete.")
    print(f"Knowledge base: {len(articles)} articles")
    print(f"This run: {created} created, {updated} updated")


if __name__ == "__main__":
    main()
