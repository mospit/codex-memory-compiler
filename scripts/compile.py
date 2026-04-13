"""Compile daily conversation logs into structured knowledge articles."""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path

from config import CONCEPTS_DIR, CONNECTIONS_DIR, DAILY_DIR, DASHBOARDS_DIR, DECISIONS_DIR, GOALS_DIR, LOG_FILE, now_iso, today_iso
from utils import (
    MANAGED_BY,
    canonical_decision_id,
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
    normalize_decision_reference,
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
    open_questions: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    files_touched: list[str] = field(default_factory=list)
    tests_run: list[str] = field(default_factory=list)
    current_statuses: list[str] = field(default_factory=list)
    verification_states: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    sessions: list[SessionRecord] = field(default_factory=list)
    related_counts: Counter[str] = field(default_factory=Counter)


@dataclass(slots=True)
class DecisionAggregate:
    """Aggregated explicit decision material across sessions."""

    decision_id: str
    decision_text: str
    source_sessions: list[str] = field(default_factory=list)
    source_logs: list[str] = field(default_factory=list)
    source_types: Counter[str] = field(default_factory=Counter)
    supersedes: list[str] = field(default_factory=list)
    implemented_by: list[str] = field(default_factory=list)
    blocked_by: list[str] = field(default_factory=list)
    current_statuses: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    files_touched: list[str] = field(default_factory=list)
    tests_run: list[str] = field(default_factory=list)
    verification_states: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    related_counts: Counter[str] = field(default_factory=Counter)


@dataclass(slots=True)
class GoalAggregate:
    """Aggregated goal-oriented material across sessions."""

    goal_id: str
    goal_text: str
    source_sessions: list[str] = field(default_factory=list)
    source_logs: list[str] = field(default_factory=list)
    source_types: Counter[str] = field(default_factory=Counter)
    workspaces: list[str] = field(default_factory=list)
    repos: list[str] = field(default_factory=list)
    task_refs: list[str] = field(default_factory=list)
    current_statuses: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    files_touched: list[str] = field(default_factory=list)
    tests_run: list[str] = field(default_factory=list)
    verification_states: list[str] = field(default_factory=list)
    related_concepts: Counter[str] = field(default_factory=Counter)
    related_decisions: list[str] = field(default_factory=list)


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


def format_daily_ref(session, line_number: int | None) -> str:
    """Render a daily-log reference with an absolute line number when known."""
    if line_number:
        return f"{session.article_source}:{line_number}"
    return session.article_source


def build_session_evidence(session) -> list[str]:
    """Return concrete evidence bullets for a session, preferring explicit evidence and validation."""
    bullets: list[str] = []
    priorities = ("evidence_excerpts", "tests_run", "decisions")
    line_refs = getattr(session, "line_refs", {}) or {}
    for key in priorities:
        for item in line_refs.get(key, []):
            text = getattr(item, "text", str(item))
            line_number = getattr(item, "line_number", None)
            if not text or text.startswith("No explicit"):
                continue
            bullets.append(
                f"{format_daily_ref(session, line_number)} / `{session.session_id}` ({session.source_type}): "
                f"{trim_sentence(text, 220)}"
            )

    if bullets:
        return unique_preserve_order(bullets)[:4]

    return [
        f"{format_daily_ref(session, getattr(session, 'context_line_number', None))} / `{session.session_id}` ({session.source_type}): "
        f"{trim_sentence(session.context, 220)}"
    ]


def build_decision_evidence(session, decision_text: str) -> list[str]:
    """Return evidence bullets for one explicit decision without leaking sibling decisions."""
    bullets: list[str] = []
    line_refs = getattr(session, "line_refs", {}) or {}
    target_id = canonical_decision_id(decision_text)

    for item in line_refs.get("decisions", []):
        text = getattr(item, "text", str(item))
        line_number = getattr(item, "line_number", None)
        if canonical_decision_id(text) != target_id:
            continue
        bullets.append(
            f"{format_daily_ref(session, line_number)} / `{session.session_id}` ({session.source_type}): "
            f"{trim_sentence(text, 220)}"
        )

    for key in ("evidence_excerpts", "tests_run"):
        for item in line_refs.get(key, []):
            text = getattr(item, "text", str(item))
            line_number = getattr(item, "line_number", None)
            if not text or text.startswith("No explicit"):
                continue
            bullets.append(
                f"{format_daily_ref(session, line_number)} / `{session.session_id}` ({session.source_type}): "
                f"{trim_sentence(text, 220)}"
            )

    if bullets:
        return unique_preserve_order(bullets)[:6]

    return [
        f"{format_daily_ref(session, getattr(session, 'context_line_number', None))} / `{session.session_id}` ({session.source_type}): "
        f"{trim_sentence(decision_text, 220)}"
    ]


def latest_nonempty(items: list[str]) -> str | None:
    """Return the latest non-empty value from an ordered list."""
    for item in reversed(items):
        cleaned = item.strip()
        if cleaned:
            return cleaned
    return None


def parse_decision_links(lines: list[str]) -> dict[str, list[str]]:
    """Parse structured decision relation lines into normalized buckets."""
    relations = {"supersedes": [], "implemented_by": [], "blocked_by": []}
    for raw in lines:
        if ":" not in raw:
            continue
        kind, value = raw.split(":", 1)
        normalized_kind = kind.strip().lower().replace("-", "_").replace(" ", "_")
        if normalized_kind not in relations:
            continue
        candidates = [item.strip() for item in re.split(r"\s*,\s*", value) if item.strip()]
        for candidate in candidates:
            if normalized_kind == "supersedes":
                decision_ref = normalize_decision_reference(candidate)
                relations[normalized_kind].append(decision_ref or candidate)
            else:
                relations[normalized_kind].append(candidate)

    return {key: unique_preserve_order(value) for key, value in relations.items()}


def session_goal_identity(session) -> tuple[str, str] | None:
    """Return a stable goal id/title pair when the session has explicit goal material."""
    goal_text = (getattr(session, "goal", None) or "").strip()
    current_status = (getattr(session, "current_status", None) or "").strip()
    open_questions = list(getattr(session, "open_questions", []) or [])
    if not goal_text and not current_status and not open_questions:
        return None

    base = session.task_ref or goal_text or session.title
    goal_id = slugify(base) or canonical_concept_id(base, goal_text, current_status)
    title = goal_text or humanize_slug(goal_id)
    return goal_id, title


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
    aggregate.open_questions = unique_preserve_order([*aggregate.open_questions, *getattr(session, "open_questions", [])])
    aggregate.blockers = unique_preserve_order([*aggregate.blockers, *getattr(session, "blockers", [])])
    aggregate.files_touched = unique_preserve_order([*aggregate.files_touched, *getattr(session, "files_touched", [])])
    aggregate.tests_run = unique_preserve_order([*aggregate.tests_run, *getattr(session, "tests_run", [])])
    if getattr(session, "current_status", None):
        aggregate.current_statuses.append(session.current_status)
    if getattr(session, "verification_state", None):
        aggregate.verification_states.append(session.verification_state)
    aggregate.workspaces = unique_preserve_order(
        [*aggregate.workspaces, *([session.workspace] if session.workspace else [])]
    )
    aggregate.repos = unique_preserve_order([*aggregate.repos, *([session.repo] if session.repo else [])])
    aggregate.task_refs = unique_preserve_order(
        [*aggregate.task_refs, *([session.task_ref] if session.task_ref else [])]
    )

    aggregate.evidence = unique_preserve_order([*aggregate.evidence, *build_session_evidence(session)])
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


def build_decision_aggregates(
    session_lookup: dict[str, CompiledSession],
    session_mentions: dict[str, list[str]],
) -> dict[str, DecisionAggregate]:
    """Aggregate explicit decisions across sessions into stable decision records."""
    aggregates: dict[str, DecisionAggregate] = {}
    for session_id, compiled in session_lookup.items():
        session = compiled.session
        decision_items = (getattr(session, "line_refs", {}) or {}).get("decisions", [])
        if not decision_items:
            continue
        relation_map = parse_decision_links(getattr(session, "decision_links", []) or [])

        for item in decision_items:
            decision_text = getattr(item, "text", str(item))
            decision_id = canonical_decision_id(decision_text)
            aggregate = aggregates.setdefault(
                decision_id,
                DecisionAggregate(decision_id=decision_id, decision_text=decision_text),
            )
            aggregate.source_sessions = unique_preserve_order([*aggregate.source_sessions, session.session_id])
            aggregate.source_logs = unique_preserve_order([*aggregate.source_logs, session.article_source])
            aggregate.source_types.update([session.source_type])
            aggregate.supersedes = unique_preserve_order([*aggregate.supersedes, *relation_map["supersedes"]])
            aggregate.implemented_by = unique_preserve_order([*aggregate.implemented_by, *relation_map["implemented_by"]])
            aggregate.blocked_by = unique_preserve_order([*aggregate.blocked_by, *relation_map["blocked_by"]])
            if getattr(session, "current_status", None):
                aggregate.current_statuses.append(session.current_status)
            aggregate.open_questions = unique_preserve_order(
                [*aggregate.open_questions, *getattr(session, "open_questions", [])]
            )
            aggregate.files_touched = unique_preserve_order(
                [*aggregate.files_touched, *getattr(session, "files_touched", [])]
            )
            aggregate.tests_run = unique_preserve_order([*aggregate.tests_run, *getattr(session, "tests_run", [])])
            if getattr(session, "verification_state", None):
                aggregate.verification_states.append(session.verification_state)
            aggregate.evidence = unique_preserve_order(
                [*aggregate.evidence, *build_decision_evidence(session, decision_text)]
            )
            for concept_id in session_mentions.get(session_id, []):
                aggregate.related_counts[concept_id] += 1

    return aggregates


def build_goal_aggregates(
    session_lookup: dict[str, CompiledSession],
    session_mentions: dict[str, list[str]],
) -> dict[str, GoalAggregate]:
    """Aggregate explicit goal/status material into stable goal records."""
    aggregates: dict[str, GoalAggregate] = {}
    for session_id, compiled in session_lookup.items():
        session = compiled.session
        goal_identity = session_goal_identity(session)
        if not goal_identity:
            continue

        goal_id, goal_text = goal_identity
        aggregate = aggregates.setdefault(
            goal_id,
            GoalAggregate(goal_id=goal_id, goal_text=goal_text),
        )
        aggregate.source_sessions = unique_preserve_order([*aggregate.source_sessions, session.session_id])
        aggregate.source_logs = unique_preserve_order([*aggregate.source_logs, session.article_source])
        aggregate.source_types.update([session.source_type])
        aggregate.workspaces = unique_preserve_order(
            [*aggregate.workspaces, *([session.workspace] if session.workspace else [])]
        )
        aggregate.repos = unique_preserve_order([*aggregate.repos, *([session.repo] if session.repo else [])])
        aggregate.task_refs = unique_preserve_order([*aggregate.task_refs, *([session.task_ref] if session.task_ref else [])])
        if getattr(session, "current_status", None):
            aggregate.current_statuses.append(session.current_status)
        aggregate.next_steps = unique_preserve_order([*aggregate.next_steps, *getattr(session, "actions", [])])
        aggregate.open_questions = unique_preserve_order(
            [*aggregate.open_questions, *getattr(session, "open_questions", [])]
        )
        aggregate.blockers = unique_preserve_order([*aggregate.blockers, *getattr(session, "blockers", [])])
        aggregate.files_touched = unique_preserve_order(
            [*aggregate.files_touched, *getattr(session, "files_touched", [])]
        )
        aggregate.tests_run = unique_preserve_order([*aggregate.tests_run, *getattr(session, "tests_run", [])])
        if getattr(session, "verification_state", None):
            aggregate.verification_states.append(session.verification_state)
        aggregate.related_decisions = unique_preserve_order(
            [*aggregate.related_decisions, *[canonical_decision_id(item) for item in getattr(session, "decisions", [])]]
        )
        for concept_id in session_mentions.get(session_id, []):
            aggregate.related_concepts[concept_id] += 1

    return aggregates


def choose_summary(aggregate: ConceptAggregate) -> str:
    """Pick a stable concept summary."""
    current_status = latest_nonempty(aggregate.current_statuses)
    if current_status:
        return trim_sentence(current_status, 160)
    if aggregate.decisions:
        return trim_sentence(aggregate.decisions[0], 160)
    if aggregate.tests_run:
        return trim_sentence(aggregate.tests_run[0], 160)
    if aggregate.contexts:
        return trim_sentence(aggregate.contexts[0], 160)
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


def latest_source_date(source_logs: list[str]) -> str:
    """Return the latest date encoded in a list of daily-log source paths."""
    dates = []
    for source in source_logs:
        stem = Path(source).stem
        if len(stem) == 10 and stem[4] == "-" and stem[7] == "-":
            dates.append(stem)
    return max(dates) if dates else today_iso()


def goal_summary(aggregate: GoalAggregate) -> str:
    """Return a concise goal summary anchored on the latest known status."""
    current_status = latest_nonempty(aggregate.current_statuses)
    if current_status:
        return trim_sentence(current_status, 160)
    if aggregate.next_steps:
        return trim_sentence(aggregate.next_steps[0], 160)
    if aggregate.open_questions:
        return trim_sentence(aggregate.open_questions[0], 160)
    return f"Goal record for {aggregate.goal_text}."


def real_followup_actions(aggregate: ConceptAggregate) -> list[str]:
    """Return real follow-up actions, excluding placeholder copy."""
    return [
        item
        for item in aggregate.actions
        if item and item.strip().lower() != "no follow-up actions captured yet."
    ]


def strip_wikilinks(text: str) -> str:
    """Replace wikilinks with plain display text for headings and titles."""
    return re.sub(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", lambda match: match.group(2) or match.group(1), text)


def write_goal_articles(
    goal_aggregates: dict[str, GoalAggregate],
) -> tuple[list[str], list[str]]:
    """Write deterministic goal pages and return created/updated links."""
    existing = managed_article_paths(GOALS_DIR)
    desired_stems: set[str] = set()
    created_links: list[str] = []
    updated_links: list[str] = []

    for goal_id in sorted(goal_aggregates):
        aggregate = goal_aggregates[goal_id]
        desired_stems.add(goal_id)
        path = GOALS_DIR / f"{goal_id}.md"
        created = concept_created_date(ConceptAggregate(concept_id=goal_id, source_logs=aggregate.source_logs))
        updated = today_iso()
        current_status = latest_nonempty(aggregate.current_statuses)
        verification_state = latest_nonempty(aggregate.verification_states)
        summary = goal_summary(aggregate)
        related_concepts = [
            f"- [[concepts/{concept_id}]] - Mentioned alongside this goal in {count} session(s)"
            for concept_id, count in aggregate.related_concepts.most_common(5)
        ]
        related_decisions = [
            f"- [[decisions/{decision_id}]]"
            for decision_id in aggregate.related_decisions[:8]
        ]
        source_lines = [f"- [[{source}]]" for source in aggregate.source_logs]

        body_sections = [
            f"# {aggregate.goal_text}",
            "",
            summary,
            "",
            "## Current Status",
            *(f"- {current_status}" for current_status in ([current_status] if current_status else [])),
            "",
            "## Next Steps",
            *(f"- [ ] {item}" for item in aggregate.next_steps or ["No explicit next steps captured yet."]),
        ]
        if aggregate.open_questions:
            body_sections.extend(["", "## Open Questions", *(f"- {item}" for item in aggregate.open_questions)])
        if aggregate.blockers:
            body_sections.extend(["", "## Blockers", *(f"- {item}" for item in aggregate.blockers)])
        if aggregate.files_touched:
            body_sections.extend(["", "## Files", *(f"- {item}" for item in aggregate.files_touched)])
        if aggregate.tests_run:
            body_sections.extend(["", "## Validation", *(f"- {item}" for item in aggregate.tests_run)])
        if verification_state:
            body_sections.extend(["", "## Verification State", f"- {verification_state}"])
        body_sections.extend(
            [
                "",
                "## Related Decisions",
                *(related_decisions or ["- None yet."]),
                "",
                "## Related Concepts",
                *(related_concepts or ["- None yet."]),
                "",
                "## Sources",
                *(source_lines or ["- None yet."]),
            ]
        )

        frontmatter = {
            "managed_by": MANAGED_BY,
            "schema_version": "2",
            "title": aggregate.goal_text,
            "goal_id": goal_id,
            "summary": summary,
            "current_status": current_status or "",
            "next_steps": aggregate.next_steps,
            "open_questions": aggregate.open_questions,
            "verification_state": verification_state or "",
            "files_touched": aggregate.files_touched,
            "tests_run": aggregate.tests_run,
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

        link = f"[[goals/{goal_id}]]"
        if goal_id in existing:
            updated_links.append(link)
        else:
            created_links.append(link)

    remove_stale_managed_articles(GOALS_DIR, desired_stems)
    return created_links, updated_links


def write_decision_articles(
    decision_aggregates: dict[str, DecisionAggregate],
) -> tuple[list[str], list[str]]:
    """Write deterministic decision pages and return created/updated links."""
    existing = managed_article_paths(DECISIONS_DIR)
    desired_stems: set[str] = set()
    created_links: list[str] = []
    updated_links: list[str] = []
    superseded_by_map: dict[str, list[str]] = defaultdict(list)

    for decision_id, aggregate in decision_aggregates.items():
        for target in aggregate.supersedes:
            normalized = normalize_decision_reference(target) or target
            superseded_by_map[normalized].append(decision_id)

    for decision_id in sorted(decision_aggregates):
        aggregate = decision_aggregates[decision_id]
        desired_stems.add(decision_id)
        path = DECISIONS_DIR / f"{decision_id}.md"
        created = concept_created_date(
            ConceptAggregate(concept_id=decision_id, source_logs=aggregate.source_logs)
        )
        updated = today_iso()
        current_status = latest_nonempty(aggregate.current_statuses)
        verification_state = latest_nonempty(aggregate.verification_states)
        superseded_by = unique_preserve_order(superseded_by_map.get(decision_id, []))
        title = trim_sentence(strip_wikilinks(aggregate.decision_text), 100)
        summary = trim_sentence(aggregate.decision_text, 160)
        related_lines = [
            f"- [[concepts/{concept_id}]] - Mentioned alongside this decision in {count} session(s)"
            for concept_id, count in aggregate.related_counts.most_common(5)
        ]
        source_lines = [f"- [[{source}]]" for source in aggregate.source_logs]
        body_sections = [
            f"# {title}",
            "",
            summary,
            "",
            "## Decision",
            f"- {aggregate.decision_text}",
        ]

        if current_status:
            body_sections.extend(["", "## Current Status", f"- {current_status}"])
        if aggregate.supersedes or aggregate.implemented_by or aggregate.blocked_by or superseded_by:
            body_sections.extend(["", "## Decision Links"])
            if aggregate.supersedes:
                for item in aggregate.supersedes:
                    normalized = normalize_decision_reference(item)
                    body_sections.append(
                        f"- supersedes: [[decisions/{normalized}]]" if normalized else f"- supersedes: {item}"
                    )
            if superseded_by:
                body_sections.extend(f"- superseded_by: [[decisions/{item}]]" for item in superseded_by)
            if aggregate.implemented_by:
                body_sections.extend(f"- implemented_by: {item}" for item in aggregate.implemented_by)
            if aggregate.blocked_by:
                body_sections.extend(f"- blocked_by: {item}" for item in aggregate.blocked_by)
        if aggregate.open_questions:
            body_sections.extend(["", "## Open Questions", *(f"- {item}" for item in aggregate.open_questions)])
        if aggregate.files_touched:
            body_sections.extend(["", "## Files", *(f"- {item}" for item in aggregate.files_touched)])
        if aggregate.tests_run:
            body_sections.extend(["", "## Validation", *(f"- {item}" for item in aggregate.tests_run)])
        if verification_state:
            body_sections.extend(["", "## Verification State", f"- {verification_state}"])

        body_sections.extend(
            [
                "",
                "## Rationale / Evidence",
                *(f"- {item}" for item in aggregate.evidence[:6]),
                "",
                "## Related Concepts",
                *(related_lines or ["- None yet."]),
                "",
                "## Sources",
                *(source_lines or ["- None yet."]),
            ]
        )

        frontmatter = {
            "managed_by": MANAGED_BY,
            "schema_version": "2",
            "title": title,
            "decision_id": decision_id,
            "summary": summary,
            "current_status": current_status or "",
            "verification_state": verification_state or "",
            "supersedes": aggregate.supersedes,
            "implemented_by": aggregate.implemented_by,
            "blocked_by": aggregate.blocked_by,
            "superseded_by": superseded_by,
            "open_questions": aggregate.open_questions,
            "files_touched": aggregate.files_touched,
            "tests_run": aggregate.tests_run,
            "source_sessions": aggregate.source_sessions,
            "source_logs": aggregate.source_logs,
            "source_types": sorted(aggregate.source_types),
            "created": created,
            "updated": updated,
        }
        write_markdown_article(path, frontmatter, "\n".join(body_sections))

        link = f"[[decisions/{decision_id}]]"
        if decision_id in existing:
            updated_links.append(link)
        else:
            created_links.append(link)

    remove_stale_managed_articles(DECISIONS_DIR, desired_stems)
    return created_links, updated_links


def write_dashboard_articles(
    aggregates: dict[str, ConceptAggregate],
    goal_aggregates: dict[str, GoalAggregate],
    decision_aggregates: dict[str, DecisionAggregate],
    session_lookup: dict[str, CompiledSession],
) -> tuple[list[str], list[str]]:
    """Write the stable Obsidian dashboard page and return created/updated links."""
    existing = managed_article_paths(DASHBOARDS_DIR)
    desired_stems = {"open-followups"}

    followup_groups: list[tuple[str, str, str, list[str], list[str], list[str]]] = []
    for concept_id, aggregate in aggregates.items():
        actions = real_followup_actions(aggregate)
        if not actions:
            continue
        followup_groups.append(
            (
                latest_source_date(aggregate.source_logs),
                humanize_slug(concept_id),
                concept_id,
                actions,
                aggregate.source_sessions,
                aggregate.source_logs,
            )
        )
    followup_groups.sort(key=lambda item: item[1])
    followup_groups.sort(key=lambda item: item[0], reverse=True)

    recent_decisions: list[tuple[str, str, DecisionAggregate]] = []
    for decision_id, aggregate in decision_aggregates.items():
        recent_decisions.append(
            (
                latest_source_date(aggregate.source_logs),
                trim_sentence(aggregate.decision_text, 100),
                aggregate,
            )
        )
    recent_decisions.sort(key=lambda item: item[1])
    recent_decisions.sort(key=lambda item: item[0], reverse=True)
    recent_decisions = recent_decisions[:25]

    active_goals: list[tuple[str, str, GoalAggregate]] = []
    for goal_id, aggregate in goal_aggregates.items():
        active_goals.append((latest_source_date(aggregate.source_logs), aggregate.goal_text, aggregate))
    active_goals.sort(key=lambda item: item[1])
    active_goals.sort(key=lambda item: item[0], reverse=True)
    active_goals = active_goals[:20]

    source_sessions: list[str] = []
    source_logs: list[str] = []
    goal_lines: list[str] = []
    for _, _, aggregate in active_goals:
        current_status = latest_nonempty(aggregate.current_statuses) or "No current status captured yet."
        goal_lines.append(f"- [[goals/{aggregate.goal_id}]] - {trim_sentence(current_status, 160)}")
        source_sessions = unique_preserve_order([*source_sessions, *aggregate.source_sessions])
        source_logs = unique_preserve_order([*source_logs, *aggregate.source_logs])

    followup_lines: list[str] = []
    for _, _, concept_id, actions, concept_sessions, concept_logs in followup_groups:
        followup_lines.extend(f"- [[concepts/{concept_id}]]: {action}" for action in actions)
        source_sessions = unique_preserve_order([*source_sessions, *concept_sessions])
        source_logs = unique_preserve_order([*source_logs, *concept_logs])

    decision_lines: list[str] = []
    for _, _, aggregate in recent_decisions:
        decision_lines.append(
            f"- [[decisions/{aggregate.decision_id}]] - {trim_sentence(aggregate.decision_text, 160)}"
        )
        source_sessions = unique_preserve_order([*source_sessions, *aggregate.source_sessions])
        source_logs = unique_preserve_order([*source_logs, *aggregate.source_logs])

    if not source_sessions or not source_logs:
        fallback_sessions = [compiled.session.session_id for compiled in session_lookup.values()]
        fallback_logs = [compiled.session.article_source for compiled in session_lookup.values()]
        source_sessions = unique_preserve_order([*source_sessions, *fallback_sessions])
        source_logs = unique_preserve_order([*source_logs, *fallback_logs])

    created = min((Path(source).stem for source in source_logs), default=today_iso())
    updated = today_iso()
    path = DASHBOARDS_DIR / "open-followups.md"
    body_sections = [
        "# Open Follow-Ups",
        "",
        "_Generated by codex-memory-compiler. Do not edit this page directly._",
    ]
    if goal_lines:
        body_sections.extend(
            [
                "",
                "## Active Goals",
                *goal_lines,
            ]
        )
    body_sections.extend(
        [
        "",
        "## Open Follow-Ups",
        *(followup_lines or ["- No open follow-ups captured yet."]),
        "",
        "## Recent Decisions",
        *(decision_lines or ["- No recent decisions captured yet."]),
        ]
    )
    dashboard_summary = (
        "Generated dashboard for active goals, open follow-ups, and recent decisions."
        if goal_lines
        else "Generated dashboard for open follow-ups and recent decisions."
    )
    dashboard_keywords = (
        ["dashboard", "goals", "followups", "decisions", "obsidian", "open"]
        if goal_lines
        else ["dashboard", "followups", "decisions", "obsidian", "open"]
    )
    frontmatter = {
        "managed_by": MANAGED_BY,
        "schema_version": "2",
        "title": "Open Follow-Ups",
        "summary": dashboard_summary,
        "keywords": dashboard_keywords,
        "source_sessions": source_sessions,
        "source_logs": source_logs,
        "created": created,
        "updated": updated,
    }
    write_markdown_article(path, frontmatter, "\n".join(body_sections))
    remove_stale_managed_articles(DASHBOARDS_DIR, desired_stems)

    link = "[[dashboards/open-followups]]"
    if "open-followups" in existing:
        return [], [link]
    return [link], []


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
        ]

        current_status = latest_nonempty(aggregate.current_statuses)
        verification_state = latest_nonempty(aggregate.verification_states)
        if current_status:
            body_sections.extend(["", "## Current Status", f"- {current_status}"])
        if aggregate.open_questions:
            body_sections.extend(["", "## Open Questions", *(f"- {item}" for item in aggregate.open_questions)])
        if aggregate.blockers:
            body_sections.extend(["", "## Blockers", *(f"- {item}" for item in aggregate.blockers)])
        if aggregate.files_touched:
            body_sections.extend(["", "## Files", *(f"- {item}" for item in aggregate.files_touched)])
        if aggregate.tests_run:
            body_sections.extend(["", "## Validation", *(f"- {item}" for item in aggregate.tests_run)])
        if verification_state:
            body_sections.extend(["", "## Verification State", f"- {verification_state}"])

        body_sections.extend(
            [
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
        )

        frontmatter = {
            "managed_by": MANAGED_BY,
            "schema_version": "2",
            "title": title,
            "concept_id": concept_id,
            "aliases": aggregate.aliases,
            "keywords": keywords,
            "summary": summary,
            "current_status": current_status or "",
            "open_questions": aggregate.open_questions,
            "verification_state": verification_state or "",
            "files_touched": aggregate.files_touched,
            "tests_run": aggregate.tests_run,
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
    decision_aggregates = build_decision_aggregates(session_lookup, session_mentions)
    goal_aggregates = build_goal_aggregates(session_lookup, session_mentions)

    if dry_run:
        concept_count = len(aggregates)
        connection_count = sum(1 for sessions in pair_sessions.values() if len(sessions) >= CONNECTION_THRESHOLD)
        goal_count = len(goal_aggregates)
        decision_count = len(decision_aggregates)
        dashboard_count = 1
        print(f"[DRY RUN] Dashboard pages: {dashboard_count}")
        print(f"[DRY RUN] Goal pages: {goal_count}")
        print(f"[DRY RUN] Decision pages: {decision_count}")
        print(f"[DRY RUN] Concept pages: {concept_count}")
        print(f"[DRY RUN] Connection pages: {connection_count}")
        print(f"[DRY RUN] Sessions parsed: {len(session_lookup)}")
        return dashboard_count + goal_count + decision_count + concept_count, connection_count

    goal_created, goal_updated = write_goal_articles(goal_aggregates)
    decision_created, decision_updated = write_decision_articles(decision_aggregates)
    concept_created, concept_updated = write_concept_articles(aggregates, pair_sessions)
    connection_created, connection_updated = write_connection_articles(aggregates, pair_sessions, session_lookup)
    dashboard_created, dashboard_updated = write_dashboard_articles(aggregates, goal_aggregates, decision_aggregates, session_lookup)
    rebuild_index()

    all_created = dashboard_created + goal_created + decision_created + concept_created + connection_created
    all_updated = dashboard_updated + goal_updated + decision_updated + concept_updated + connection_updated
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
