"""Shared utilities for the personal knowledge base."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from config import (
    CONCEPTS_DIR,
    CONNECTIONS_DIR,
    DASHBOARDS_DIR,
    DAILY_DIR,
    DECISIONS_DIR,
    GOALS_DIR,
    INDEX_FILE,
    KNOWLEDGE_DIR,
    LOG_FILE,
    QA_DIR,
    STATE_FILE,
)

MANAGED_BY = "codex-memory-compiler"
INDEX_HEADER = (
    "# Knowledge Base Index\n\n"
    "| Article | Type | Summary | Keywords | Sources | Updated |\n"
    "|---------|------|---------|----------|---------|---------|\n"
)

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "but",
    "by",
    "did",
    "do",
    "for",
    "from",
    "had",
    "has",
    "have",
    "how",
    "i",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "me",
    "my",
    "no",
    "not",
    "of",
    "on",
    "or",
    "our",
    "so",
    "that",
    "the",
    "their",
    "them",
    "there",
    "this",
    "to",
    "up",
    "use",
    "using",
    "was",
    "we",
    "what",
    "when",
    "where",
    "with",
    "you",
    "your",
}

GENERIC_CONCEPT_TOKENS = {
    "avoid",
    "change",
    "codex",
    "decid",
    "decision",
    "decisions",
    "disable",
    "follow",
    "followup",
    "general",
    "issue",
    "issues",
    "keep",
    "note",
    "notes",
    "plan",
    "planning",
    "prefer",
    "review",
    "session",
    "summary",
    "task",
    "todo",
    "update",
    "use",
    "work",
    "workflow",
}

TOKEN_NORMALIZATION = {
    "apis": "api",
    "auth": "authentication",
    "authenticate": "authentication",
    "authenticated": "authentication",
    "db": "database",
    "decid": "decision",
    "deps": "dependency",
    "disabl": "disable",
    "migrations": "migration",
    "prs": "pull-request",
    "pr": "pull-request",
    "repos": "repository",
    "repo": "repository",
    "shar": "shared",
    "shared": "shared",
    "tests": "test",
    "uis": "ui",
    "ux": "ux",
}

DISPLAY_TOKEN_MAP = {
    "api": "API",
    "qa": "QA",
    "ui": "UI",
    "ux": "UX",
}

POSITIVE_CUES = {"adopt", "allow", "enable", "keep", "prefer", "standardize", "use"}
NEGATIVE_CUES = {"avoid", "disable", "dont", "do-not", "drop", "never", "remove", "stop"}


@dataclass(slots=True)
class LineRef:
    """A text item with its absolute daily-log line number."""

    text: str
    line_number: int


@dataclass(slots=True)
class DailySession:
    """Normalized daily session entry."""

    log_path: Path
    log_name: str
    session_id: str
    title: str
    source_type: str
    context: str
    goal: str | None
    current_status: str | None
    key_exchanges: list[str]
    decisions: list[str]
    decision_links: list[str]
    lessons: list[str]
    actions: list[str]
    open_questions: list[str]
    blockers: list[str]
    files_touched: list[str]
    tests_run: list[str]
    verification_state: str | None
    evidence_excerpts: list[str]
    date_context: str | None
    keywords: list[str]
    workspace: str | None
    repo: str | None
    task_ref: str | None
    timestamp_label: str | None
    raw_body: str
    context_line_number: int | None = None
    date_context_line_number: int | None = None
    line_refs: dict[str, list[LineRef]] = field(default_factory=dict)

    @property
    def article_source(self) -> str:
        return f"daily/{self.log_name}"

    @property
    def full_text(self) -> str:
        parts = [
            self.title,
            self.context,
            self.goal or "",
            self.current_status or "",
            self.date_context or "",
            *self.key_exchanges,
            *self.decisions,
            *self.decision_links,
            *self.lessons,
            *self.actions,
            *self.open_questions,
            *self.blockers,
            *self.files_touched,
            *self.tests_run,
            self.verification_state or "",
            *self.evidence_excerpts,
            " ".join(self.keywords),
        ]
        return " ".join(part for part in parts if part)


@dataclass(slots=True)
class IndexEntry:
    """Parsed index row."""

    link: str
    article_type: str
    summary: str
    keywords: list[str]
    sources: list[str]
    updated: str

    @property
    def path(self) -> Path:
        return KNOWLEDGE_DIR / f"{self.link}.md"


def load_state() -> dict:
    """Load persistent state from state.json."""
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"ingested": {}, "query_count": 0, "last_lint": None, "total_cost": 0.0}


def save_state(state: dict) -> None:
    """Save state to state.json."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def file_hash(path: Path) -> str:
    """SHA-256 hash of a file (first 16 hex chars)."""
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def normalize_token(token: str) -> str:
    """Normalize a token for deterministic concept extraction."""
    token = re.sub(r"[^a-z0-9-]", "", token.lower())
    if not token:
        return ""
    token = TOKEN_NORMALIZATION.get(token, token)

    if token.endswith("ies") and len(token) > 4:
        token = token[:-3] + "y"
    elif token.endswith("ing") and len(token) > 6:
        token = token[:-3]
    elif token.endswith("ed") and len(token) > 5:
        token = token[:-2]
    elif token.endswith("s") and len(token) > 4 and not token.endswith("ss"):
        token = token[:-1]

    return TOKEN_NORMALIZATION.get(token, token)


def tokenize(text: str, *, drop_generic: bool = True) -> list[str]:
    """Convert text to normalized lexical tokens."""
    raw_tokens = re.findall(r"[a-zA-Z0-9-]+", text.lower())
    tokens: list[str] = []
    for raw in raw_tokens:
        pieces = raw.split("-") if "-" in raw else [raw]
        for piece in pieces:
            normalized = normalize_token(piece)
            if len(normalized) < 3:
                continue
            if normalized in STOPWORDS:
                continue
            if drop_generic and normalized in GENERIC_CONCEPT_TOKENS:
                continue
            tokens.append(normalized)
    return tokens


def slugify(text: str) -> str:
    """Convert text to a filename-safe slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


def humanize_slug(slug: str) -> str:
    """Convert a slug into a human-readable title."""
    parts = [part for part in slug.split("-") if part]
    if not parts:
        return "Untitled"
    rendered = [DISPLAY_TOKEN_MAP.get(part, part.capitalize()) for part in parts]
    return " ".join(rendered)


def unique_preserve_order(items: list[str]) -> list[str]:
    """Return unique values while preserving the first appearance order."""
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        clean = item.strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        result.append(clean)
    return result


def trim_sentence(text: str, max_chars: int = 220) -> str:
    """Trim text to a deterministic sentence-like preview."""
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def is_weak_summary(text: str) -> bool:
    """Return whether a summary is too weak for reliable retrieval."""
    summary = re.sub(r"\s+", " ", text).strip()
    if len(summary) < 40:
        return True
    if summary.lower().startswith("no summary"):
        return True
    if summary.endswith("..."):
        return True
    return False


def extract_keywords(*weighted_texts: tuple[str, int], limit: int = 6) -> list[str]:
    """Extract ordered keywords from weighted text inputs."""
    counter: Counter[str] = Counter()
    first_seen: dict[str, tuple[int, int]] = {}

    for source_index, (text, weight) in enumerate(weighted_texts):
        for token_index, token in enumerate(tokenize(text)):
            counter[token] += weight
            first_seen.setdefault(token, (source_index, token_index))

    ranked = sorted(
        counter,
        key=lambda token: (-counter[token], first_seen[token][0], first_seen[token][1], token),
    )
    return ranked[:limit]


def derive_title_from_text(text: str) -> str:
    """Derive a human title when the operator does not provide one."""
    keywords = extract_keywords((text, 3), limit=4)
    if keywords:
        return humanize_slug("-".join(keywords))

    clean = trim_sentence(text, max_chars=60)
    clean = re.sub(r"[^\w\s-]", "", clean)
    return clean.title() or "Session Note"


def canonical_concept_id(title: str, *supporting_text: str) -> str:
    """Derive a stable concept identifier from title and supporting context."""
    keywords = extract_keywords((title, 5), *((text, 2) for text in supporting_text), limit=3)
    if len(keywords) >= 2:
        return "-".join(keywords[:2])
    if keywords:
        fallback_keywords = extract_keywords((title, 5), *((text, 2) for text in supporting_text), limit=4)
        if len(fallback_keywords) >= 2:
            return "-".join(fallback_keywords[:2])
        return keywords[0]

    fallback = slugify(title)
    return fallback or "session-concept"


def canonical_decision_id(text: str) -> str:
    """Derive a stable identifier for an explicit decision line."""
    normalized = " ".join(tokenize(text, drop_generic=False))
    return slugify(normalized) or "decision-record"


def extract_wikilinks(content: str) -> list[str]:
    """Extract all [[wikilinks]] from markdown content."""
    return re.findall(r"\[\[([^\]]+)\]\]", content)


def extract_wikilink_targets(text: str) -> list[str]:
    """Extract wikilink targets from free-form text."""
    return re.findall(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", text)


def normalize_decision_reference(text: str) -> str | None:
    """Normalize a wikilink or raw decision reference into a decision id."""
    for target in extract_wikilink_targets(text):
        if target.startswith("decisions/"):
            return target.split("/", 1)[1].strip() or None

    cleaned = text.strip()
    if cleaned.startswith("decisions/"):
        return cleaned.split("/", 1)[1].strip() or None

    return None


def wiki_article_exists(link: str) -> bool:
    """Check if a wikilinked article exists on disk."""
    path = KNOWLEDGE_DIR / f"{link}.md"
    return path.exists()


def as_list(value: Any) -> list[str]:
    """Normalize scalars and lists into a string list."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return []
        if "," in cleaned:
            return [part.strip() for part in cleaned.split(",") if part.strip()]
        return [cleaned]
    return [str(value).strip()]


def parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """Parse a constrained YAML frontmatter block."""
    if not content.startswith("---\n"):
        return {}, content

    closing = content.find("\n---\n", 4)
    if closing == -1:
        return {}, content

    raw_frontmatter = content[4:closing]
    body = content[closing + 5 :]
    frontmatter: dict[str, Any] = {}
    current_key: str | None = None

    for line in raw_frontmatter.splitlines():
        if not line.strip():
            continue

        if line.startswith("  - ") and current_key:
            frontmatter.setdefault(current_key, []).append(_strip_yaml_value(line[4:]))
            continue

        match = re.match(r"^([A-Za-z0-9_-]+):(?:\s*(.*))?$", line)
        if not match:
            current_key = None
            continue

        current_key = match.group(1)
        raw_value = (match.group(2) or "").strip()
        if not raw_value:
            frontmatter[current_key] = []
            continue

        frontmatter[current_key] = _parse_yaml_value(raw_value)
        current_key = None

    return frontmatter, body.lstrip("\n")


def _strip_yaml_value(value: str) -> str:
    value = value.strip()
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    return value


def _parse_yaml_value(value: str) -> Any:
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_strip_yaml_value(part) for part in inner.split(",")]
    return _strip_yaml_value(value)


def dump_frontmatter(frontmatter: dict[str, Any]) -> str:
    """Serialize constrained YAML frontmatter."""
    lines = ["---"]
    for key, value in frontmatter.items():
        if isinstance(value, list):
            if not value:
                lines.append(f"{key}: []")
            else:
                lines.append(f"{key}:")
                lines.extend(f'  - "{_yaml_escape(item)}"' for item in value)
            continue
        rendered = _yaml_escape(value)
        lines.append(f'{key}: "{rendered}"' if _needs_quotes(rendered) else f"{key}: {rendered}")
    lines.append("---")
    return "\n".join(lines)


def _needs_quotes(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return any(ch in value for ch in [":", "[", "]", "{", "}", "#"]) or value.strip() != value


def _yaml_escape(value: Any) -> str:
    return str(value).replace('"', "'")


def read_markdown_article(path: Path) -> tuple[dict[str, Any], str]:
    """Read a markdown file with optional frontmatter."""
    return parse_frontmatter(path.read_text(encoding="utf-8"))


def write_markdown_article(path: Path, frontmatter: dict[str, Any], body: str) -> None:
    """Write a markdown article with frontmatter."""
    path.parent.mkdir(parents=True, exist_ok=True)
    content = dump_frontmatter(frontmatter).rstrip() + "\n\n" + body.strip() + "\n"
    path.write_text(content, encoding="utf-8")


def list_wiki_articles() -> list[Path]:
    """List all wiki article files."""
    articles: list[Path] = []
    for subdir in [DASHBOARDS_DIR, GOALS_DIR, DECISIONS_DIR, CONCEPTS_DIR, CONNECTIONS_DIR, QA_DIR]:
        if subdir.exists():
            articles.extend(sorted(subdir.glob("*.md")))
    return articles


def list_raw_files() -> list[Path]:
    """List all daily log files."""
    if not DAILY_DIR.exists():
        return []
    return sorted(DAILY_DIR.glob("*.md"))


def count_inbound_links(target: str, exclude_file: Path | None = None) -> int:
    """Count how many wiki articles link to a given target."""
    count = 0
    for article in list_wiki_articles():
        if article == exclude_file:
            continue
        content = article.read_text(encoding="utf-8")
        if f"[[{target}]]" in content:
            count += 1
    return count


def get_article_word_count(path: Path) -> int:
    """Count words in an article, excluding YAML frontmatter."""
    _, body = read_markdown_article(path)
    return len(body.split())


def ensure_knowledge_scaffold() -> None:
    """Create the knowledge directories and base scaffold."""
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    DASHBOARDS_DIR.mkdir(parents=True, exist_ok=True)
    GOALS_DIR.mkdir(parents=True, exist_ok=True)
    DECISIONS_DIR.mkdir(parents=True, exist_ok=True)
    CONCEPTS_DIR.mkdir(parents=True, exist_ok=True)
    CONNECTIONS_DIR.mkdir(parents=True, exist_ok=True)
    QA_DIR.mkdir(parents=True, exist_ok=True)

    if not INDEX_FILE.exists():
        INDEX_FILE.write_text(INDEX_HEADER, encoding="utf-8")

    if not LOG_FILE.exists():
        LOG_FILE.write_text("# Build Log\n\n", encoding="utf-8")


def article_type_for_path(path: Path) -> str:
    """Return the article type name for a knowledge path."""
    rel = path.relative_to(KNOWLEDGE_DIR).as_posix()
    prefix = rel.split("/", 1)[0]
    return {
        "dashboards": "dashboard",
        "goals": "goal",
        "decisions": "decision",
        "concepts": "concept",
        "connections": "connection",
        "qa": "qa",
    }.get(prefix, "article")


def _article_summary(frontmatter: dict[str, Any], body: str) -> str:
    if frontmatter.get("summary"):
        return trim_sentence(str(frontmatter["summary"]), max_chars=140)

    for line in body.splitlines():
        clean = line.strip()
        if clean and not clean.startswith("#") and not clean.startswith("-"):
            return trim_sentence(clean, max_chars=140)
    return "No summary available."


def build_index_entry(path: Path) -> IndexEntry:
    """Build a single index entry from a markdown article."""
    frontmatter, body = read_markdown_article(path)
    rel = path.relative_to(KNOWLEDGE_DIR).as_posix().replace(".md", "")
    keywords = as_list(frontmatter.get("keywords"))
    sources = as_list(frontmatter.get("source_logs")) or as_list(frontmatter.get("consulted"))
    updated = str(frontmatter.get("updated") or frontmatter.get("filed") or "")
    return IndexEntry(
        link=rel,
        article_type=article_type_for_path(path),
        summary=_article_summary(frontmatter, body),
        keywords=keywords,
        sources=sources,
        updated=updated,
    )


def sanitize_table_cell(value: str) -> str:
    """Normalize a markdown table cell."""
    return re.sub(r"\s+", " ", value.replace("|", "/")).strip()


def rebuild_index() -> None:
    """Rebuild the markdown index from current knowledge articles."""
    ensure_knowledge_scaffold()
    rows = render_index_lines()
    INDEX_FILE.write_text("\n".join(rows).rstrip() + "\n", encoding="utf-8")


def render_index_lines() -> list[str]:
    """Render the current index into markdown lines without writing it."""
    rows = [INDEX_HEADER.rstrip()]
    type_order = {"dashboard": 0, "goal": 1, "decision": 2, "concept": 3, "connection": 4, "qa": 5, "article": 6}

    entries = [build_index_entry(path) for path in list_wiki_articles()]
    entries.sort(key=lambda entry: (type_order.get(entry.article_type, 9), entry.link))

    for entry in entries:
        keywords = ", ".join(entry.keywords[:5]) if entry.keywords else "(none)"
        sources = ", ".join(entry.sources[:3]) if entry.sources else "(none)"
        rows.append(
            "| [[{link}]] | {article_type} | {summary} | {keywords} | {sources} | {updated} |".format(
                link=entry.link,
                article_type=entry.article_type,
                summary=sanitize_table_cell(entry.summary),
                keywords=sanitize_table_cell(keywords),
                sources=sanitize_table_cell(sources),
                updated=sanitize_table_cell(entry.updated),
            )
        )

    return rows


def read_index_entries() -> list[IndexEntry]:
    """Parse `knowledge/index.md` into index rows."""
    if not INDEX_FILE.exists():
        return []

    entries: list[IndexEntry] = []
    for line in INDEX_FILE.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| [["):
            continue

        parts = [part.strip() for part in line.split("|")[1:-1]]
        if len(parts) != 6:
            continue

        link = parts[0][2:-2]
        article_type = parts[1]
        summary = parts[2]
        keywords = [] if parts[3] == "(none)" else [value.strip() for value in parts[3].split(",")]
        sources = [] if parts[4] == "(none)" else [value.strip() for value in parts[4].split(",")]
        entries.append(
            IndexEntry(
                link=link,
                article_type=article_type,
                summary=summary,
                keywords=keywords,
                sources=sources,
                updated=parts[5],
            )
        )

    return entries


def read_wiki_index() -> str:
    """Read the knowledge base index file."""
    if INDEX_FILE.exists():
        return INDEX_FILE.read_text(encoding="utf-8")
    return INDEX_HEADER


def read_all_wiki_content() -> str:
    """Read index and all wiki articles into a single string for context."""
    parts = [f"## INDEX\n\n{read_wiki_index()}"]

    for article in list_wiki_articles():
        rel = article.relative_to(KNOWLEDGE_DIR)
        content = article.read_text(encoding="utf-8")
        parts.append(f"## {rel}\n\n{content}")

    return "\n\n---\n\n".join(parts)


def line_number_for_offset(content: str, absolute_index: int) -> int:
    """Return a 1-based line number for an absolute character offset."""
    return content.count("\n", 0, absolute_index) + 1


def parse_list_section_refs(
    body: str,
    heading: str,
    *,
    full_content: str,
    body_start_offset: int,
) -> list[LineRef]:
    """Extract bullet-like section items and their absolute line numbers."""
    pattern = re.compile(
        rf"\*\*{re.escape(heading)}:\*\*\s*(.*?)"
        r"(?=\n\*\*[A-Za-z0-9 _-]+:\*\*|\Z)",
        flags=re.DOTALL,
    )
    match = pattern.search(body)
    if not match:
        return []

    items: list[LineRef] = []
    section_text = match.group(1)
    section_start = body_start_offset + match.start(1)
    offset = 0
    for line in section_text.splitlines(keepends=True):
        clean = line.strip()
        line_number = line_number_for_offset(full_content, section_start + offset)
        offset += len(line)
        if not clean:
            continue
        clean = re.sub(r"^-\s*(\[[ xX]\]\s*)?", "", clean)
        clean = clean.replace("  Assistant:", "Assistant:")
        items.append(LineRef(text=clean, line_number=line_number))
    return items


def parse_list_section(body: str, heading: str) -> list[str]:
    """Extract bullet-like section items from a daily session body."""
    return [item.text for item in parse_list_section_refs(body, heading, full_content=body, body_start_offset=0)]


def parse_scalar_section_with_line(
    body: str,
    heading: str,
    *,
    full_content: str,
    body_start_offset: int,
) -> LineRef | None:
    """Extract a single-line scalar section and its absolute line number."""
    pattern = re.compile(rf"\*\*{re.escape(heading)}:\*\*\s*(.+)$", flags=re.MULTILINE)
    match = pattern.search(body)
    if not match:
        return None
    return LineRef(
        text=match.group(1).strip(),
        line_number=line_number_for_offset(full_content, body_start_offset + match.start(1)),
    )


def parse_scalar_section(body: str, heading: str) -> str | None:
    """Extract a single-line scalar section from a daily session body."""
    item = parse_scalar_section_with_line(body, heading, full_content=body, body_start_offset=0)
    return item.text if item else None


def _fallback_context(body: str) -> str:
    for line in body.splitlines():
        clean = line.strip()
        if clean and not clean.startswith("**"):
            return trim_sentence(clean, max_chars=180)
    return "No explicit user objective found in captured context."


def parse_daily_sessions(log_path: Path) -> list[DailySession]:
    """Parse daily log entries into normalized sessions."""
    log_content = log_path.read_text(encoding="utf-8")
    heading_pattern = re.compile(r"^###\s+(.+?)(?:\s+\((\d{2}:\d{2})\))?\s*$", flags=re.MULTILINE)
    matches = list(heading_pattern.finditer(log_content))
    sessions: list[DailySession] = []

    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(log_content)
        raw_title = match.group(1).strip()
        body = log_content[start:end].strip()
        if not body:
            continue

        session_id = parse_scalar_section(body, "Session ID")
        source_type = parse_scalar_section(body, "Source Type") or "note"
        title = parse_scalar_section(body, "Title") or raw_title or "Session Note"

        body_offset = start
        context_item = parse_scalar_section_with_line(
            body,
            "Context",
            full_content=log_content,
            body_start_offset=body_offset,
        )
        goal_item = parse_scalar_section_with_line(
            body,
            "Goal",
            full_content=log_content,
            body_start_offset=body_offset,
        )
        current_status_item = parse_scalar_section_with_line(
            body,
            "Current Status",
            full_content=log_content,
            body_start_offset=body_offset,
        )
        context = context_item.text if context_item else _fallback_context(body)
        key_exchange_refs = parse_list_section_refs(
            body,
            "Key Exchanges",
            full_content=log_content,
            body_start_offset=body_offset,
        )
        decision_refs = parse_list_section_refs(
            body,
            "Decisions Made",
            full_content=log_content,
            body_start_offset=body_offset,
        )
        decision_link_refs = parse_list_section_refs(
            body,
            "Decision Links",
            full_content=log_content,
            body_start_offset=body_offset,
        )
        lesson_refs = parse_list_section_refs(
            body,
            "Lessons Learned",
            full_content=log_content,
            body_start_offset=body_offset,
        )
        action_refs = parse_list_section_refs(
            body,
            "Action Items",
            full_content=log_content,
            body_start_offset=body_offset,
        )
        open_question_refs = parse_list_section_refs(
            body,
            "Open Questions",
            full_content=log_content,
            body_start_offset=body_offset,
        )
        blocker_refs = parse_list_section_refs(
            body,
            "Blockers",
            full_content=log_content,
            body_start_offset=body_offset,
        )
        file_refs = parse_list_section_refs(
            body,
            "Files Touched",
            full_content=log_content,
            body_start_offset=body_offset,
        )
        test_refs = parse_list_section_refs(
            body,
            "Tests Run",
            full_content=log_content,
            body_start_offset=body_offset,
        )
        verification_state_item = parse_scalar_section_with_line(
            body,
            "Verification State",
            full_content=log_content,
            body_start_offset=body_offset,
        )
        evidence_refs = parse_list_section_refs(
            body,
            "Evidence Excerpts",
            full_content=log_content,
            body_start_offset=body_offset,
        )
        date_context_item = parse_scalar_section_with_line(
            body,
            "Date Context",
            full_content=log_content,
            body_start_offset=body_offset,
        )

        key_exchanges = [item.text for item in key_exchange_refs]
        decisions = [item.text for item in decision_refs]
        decision_links = [item.text for item in decision_link_refs]
        lessons = [item.text for item in lesson_refs]
        actions = [item.text for item in action_refs]
        open_questions = [item.text for item in open_question_refs]
        blockers = [item.text for item in blocker_refs]
        files_touched = [item.text for item in file_refs]
        tests_run = [item.text for item in test_refs]
        verification_state = verification_state_item.text if verification_state_item else None
        evidence_excerpts = [item.text for item in evidence_refs]
        date_context = date_context_item.text if date_context_item else None

        keywords_raw = parse_scalar_section(body, "Keywords")
        keywords = (
            [value.strip() for value in keywords_raw.split(",") if value.strip()]
            if keywords_raw
            else extract_keywords(
                (title, 4),
                (context, 3),
                (date_context or "", 2),
                (" ".join(decisions + lessons + blockers + tests_run), 2),
            )
        )

        if not session_id:
            fallback = file_hash(log_path)[:8]
            session_id = f"{log_path.stem}-{slugify(raw_title) or 'session'}-{fallback}-{index + 1}"

        sessions.append(
            DailySession(
                log_path=log_path,
                log_name=log_path.name,
                session_id=session_id,
                title=title,
                source_type=source_type,
                context=context,
                goal=goal_item.text if goal_item else None,
                current_status=current_status_item.text if current_status_item else None,
                key_exchanges=key_exchanges,
                decisions=decisions,
                decision_links=decision_links,
                lessons=lessons,
                actions=actions,
                open_questions=open_questions,
                blockers=blockers,
                files_touched=files_touched,
                tests_run=tests_run,
                verification_state=verification_state,
                evidence_excerpts=evidence_excerpts,
                date_context=date_context,
                keywords=unique_preserve_order(keywords),
                workspace=parse_scalar_section(body, "Workspace"),
                repo=parse_scalar_section(body, "Repo"),
                task_ref=parse_scalar_section(body, "Task Ref"),
                timestamp_label=match.group(2),
                raw_body=body,
                context_line_number=context_item.line_number if context_item else None,
                date_context_line_number=date_context_item.line_number if date_context_item else None,
                line_refs={
                    "key_exchanges": key_exchange_refs,
                    "decisions": decision_refs,
                    "decision_links": decision_link_refs,
                    "lessons": lesson_refs,
                    "actions": action_refs,
                    "open_questions": open_question_refs,
                    "blockers": blocker_refs,
                    "files_touched": file_refs,
                    "tests_run": test_refs,
                    "evidence_excerpts": evidence_refs,
                },
            )
        )

    return sessions


def managed_article_paths(directory: Path) -> dict[str, Path]:
    """Return managed articles keyed by file stem."""
    paths: dict[str, Path] = {}
    if not directory.exists():
        return paths

    for path in directory.glob("*.md"):
        frontmatter, _ = read_markdown_article(path)
        if frontmatter.get("managed_by") == MANAGED_BY:
            paths[path.stem] = path
    return paths


def remove_stale_managed_articles(directory: Path, desired_stems: set[str]) -> list[Path]:
    """Delete managed generated articles that are no longer present."""
    removed: list[Path] = []
    for stem, path in managed_article_paths(directory).items():
        if stem in desired_stems:
            continue
        path.unlink(missing_ok=True)
        removed.append(path)
    return removed


def parse_article_sections(body: str) -> dict[str, list[str]]:
    """Parse markdown headings into bullet lists."""
    sections: dict[str, list[str]] = defaultdict(list)
    current_heading: str | None = None
    for line in body.splitlines():
        heading = re.match(r"^##\s+(.+)$", line.strip())
        if heading:
            current_heading = heading.group(1).strip().lower()
            continue
        if current_heading and line.strip().startswith("- "):
            sections[current_heading].append(line.strip()[2:])
    return sections


def index_snapshot() -> list[str]:
    """Return current index rows for comparison during linting."""
    return [line for line in read_wiki_index().splitlines() if line.startswith("| [[")]


def polarity_subject(line: str) -> tuple[str | None, tuple[str, ...]]:
    """Return heuristic polarity and subject tokens for a decision line."""
    normalized = line.lower().replace("do not", "do-not").replace("don't", "dont")
    tokens = tokenize(normalized, drop_generic=False)
    if not tokens:
        return None, ()

    has_positive = any(token in POSITIVE_CUES for token in tokens)
    has_negative = any(token in NEGATIVE_CUES for token in tokens)
    if has_positive and has_negative:
        return None, ()
    polarity = "positive" if has_positive else "negative" if has_negative else None

    subject = tuple(token for token in tokens if token not in POSITIVE_CUES | NEGATIVE_CUES | STOPWORDS)
    return polarity, subject
