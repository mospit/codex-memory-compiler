"""Memory ingest utility for conversation context."""

from __future__ import annotations

import argparse
import json
import logging
import re
import subprocess
import sys
import time
from pathlib import Path

from config import DAILY_DIR, SCRIPTS_DIR, now_dt
from utils import derive_title_from_text, extract_keywords, trim_sentence

SCRIPT_DIR = Path(__file__).resolve().parent
STATE_FILE = SCRIPTS_DIR / "last-flush.json"
LOG_FILE = SCRIPTS_DIR / "flush.log"
SOURCE_TYPES = ("note", "codex-summary", "commit-summary", "pr-summary", "codex-chat")

SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    filename=str(LOG_FILE),
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

COMPILE_AFTER_HOUR = 18
MAX_EXCHANGES = 10
MAX_NOTE_LINES = 8


def load_flush_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_flush_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def cleanup_context_file(path: Path) -> None:
    """Delete only temporary ingest payloads created by the toolchain."""
    temp_root = (SCRIPT_DIR / ".tmp").resolve()
    try:
        if path.resolve().is_relative_to(temp_root):
            path.unlink(missing_ok=True)
    except OSError:
        return


def append_to_daily_log(content: str, title: str) -> None:
    """Append content to today's daily log."""
    today = now_dt()
    log_path = DAILY_DIR / f"{today.strftime('%Y-%m-%d')}.md"

    if not log_path.exists():
        DAILY_DIR.mkdir(parents=True, exist_ok=True)
        log_path.write_text(
            f"# Daily Log: {today.strftime('%Y-%m-%d')}\n\n## Sessions\n\n## Memory Maintenance\n\n",
            encoding="utf-8",
        )

    entry = f"### {title} ({today.strftime('%H:%M')})\n\n{content}\n\n"
    with open(log_path, "a", encoding="utf-8") as handle:
        handle.write(entry)


def parse_dialogue_turns(context: str) -> tuple[list[str], list[str]]:
    """Extract explicit user and assistant turn blocks from markdown context."""
    turns: list[tuple[str, list[str]]] = []
    current_role: str | None = None
    current_lines: list[str] = []

    def flush_current() -> None:
        nonlocal current_role, current_lines
        if not current_role:
            return
        rendered = "\n".join(current_lines).strip()
        if rendered:
            turns.append((current_role, current_lines[:]))
        current_role = None
        current_lines = []

    for raw in context.splitlines():
        stripped = raw.strip()
        user_match = re.match(r"^(?:\*\*User:\*\*|User:)\s*(.*)$", stripped, flags=re.IGNORECASE)
        if user_match:
            flush_current()
            current_role = "user"
            first_line = user_match.group(1).strip()
            current_lines = [first_line] if first_line else []
            continue

        assistant_match = re.match(
            r"^(?:\*\*Assistant:\*\*|Assistant:)\s*(.*)$",
            stripped,
            flags=re.IGNORECASE,
        )
        if assistant_match:
            flush_current()
            current_role = "assistant"
            first_line = assistant_match.group(1).strip()
            current_lines = [first_line] if first_line else []
            continue

        if current_role is not None:
            current_lines.append(raw.rstrip())

    flush_current()

    user_turns: list[str] = []
    assistant_turns: list[str] = []
    for role, raw_lines in turns:
        rendered = "\n".join(raw_lines).strip()
        if not rendered:
            continue
        if role == "assistant" and re.match(
            r"^Captured via .+ ingest workflow\.$",
            rendered,
            flags=re.IGNORECASE,
        ):
            continue
        if role == "user":
            user_turns.append(rendered)
        else:
            assistant_turns.append(rendered)

    return user_turns, assistant_turns


def parse_note_lines(context: str) -> list[str]:
    """Extract plain note lines from a context file."""
    lines: list[str] = []
    for raw in context.splitlines():
        line = raw.strip()
        if not line or line.startswith("```"):
            continue
        line = re.sub(r"^[#>*-]+\s*", "", line).strip()
        if line:
            lines.append(line)
    return lines


def build_key_exchanges(
    user_lines: list[str],
    assistant_lines: list[str],
    note_lines: list[str],
) -> list[str]:
    """Build deterministic exchange bullets from the captured context."""
    exchanges: list[str] = []

    if user_lines or assistant_lines:
        for index in range(min(MAX_EXCHANGES, max(len(user_lines), len(assistant_lines)))):
            question = user_lines[index] if index < len(user_lines) else "(no user line captured)"
            answer = (
                assistant_lines[index]
                if index < len(assistant_lines)
                else "(no assistant line captured)"
            )
            exchanges.append(f"User: {trim_sentence(question, 160)}")
            exchanges.append(f"Assistant: {trim_sentence(answer, 180)}")
        return exchanges

    return [trim_sentence(line, 180) for line in note_lines[:MAX_NOTE_LINES]]


def classify_lines(lines: list[str]) -> tuple[list[str], list[str], list[str]]:
    """Extract decisions, lessons, and action items."""
    decisions: list[str] = []
    lessons: list[str] = []
    actions: list[str] = []

    decision_terms = ("decide", "choose", "chosen", "keep", "prefer", "standardize", "use")
    lesson_terms = ("bug", "error", "failed", "issue", "learned", "note", "risk")
    action_terms = ("action", "follow up", "next", "todo", "later")

    for line in lines:
        lowered = line.lower()
        if any(term in lowered for term in decision_terms) and len(decisions) < 5:
            decisions.append(trim_sentence(line, 180))
        if any(term in lowered for term in lesson_terms) and len(lessons) < 5:
            lessons.append(trim_sentence(line, 180))
        if any(term in lowered for term in action_terms) and len(actions) < 5:
            actions.append(trim_sentence(line, 180))

    return decisions, lessons, actions


def build_structured_entry(
    context: str,
    *,
    session_id: str,
    title: str | None,
    source_type: str,
    workspace: str | None,
    repo: str | None,
    task_ref: str | None,
) -> tuple[str, str]:
    """Create deterministic structured daily-log content from context."""
    user_lines, assistant_lines = parse_dialogue_turns(context)
    note_lines = parse_note_lines(context)
    candidate_lines = user_lines + assistant_lines
    if not candidate_lines:
        candidate_lines = note_lines

    context_line = (
        trim_sentence(user_lines[0], 180)
        if user_lines
        else trim_sentence(note_lines[0], 180)
        if note_lines
        else "No explicit user objective found in captured context."
    )
    derived_title = title or derive_title_from_text(context_line)
    exchanges = build_key_exchanges(user_lines, assistant_lines, note_lines)
    decisions, lessons, actions = classify_lines(candidate_lines)
    keywords = extract_keywords(
        (derived_title, 5),
        (context_line, 4),
        (" ".join(candidate_lines), 2),
        limit=6,
    )

    parts = [
        f"**Session ID:** {session_id}",
        f"**Source Type:** {source_type}",
        f"**Title:** {derived_title}",
    ]
    if workspace:
        parts.append(f"**Workspace:** {workspace}")
    if repo:
        parts.append(f"**Repo:** {repo}")
    if task_ref:
        parts.append(f"**Task Ref:** {task_ref}")

    parts.extend(
        [
            f"**Context:** {context_line}",
            f"**Keywords:** {', '.join(keywords)}" if keywords else "**Keywords:**",
            "",
            "**Key Exchanges:**",
        ]
    )
    parts.extend(f"- {line}" for line in exchanges or ["No salient exchanges parsed."])

    if decisions:
        parts.extend(["", "**Decisions Made:**", *[f"- {line}" for line in decisions]])
    if lessons:
        parts.extend(["", "**Lessons Learned:**", *[f"- {line}" for line in lessons]])
    if actions:
        parts.extend(["", "**Action Items:**", *[f"- [ ] {line}" for line in actions]])

    return "\n".join(parts), derived_title


def maybe_trigger_compilation() -> None:
    """If it's past compile hour and today's log changed, run compile.py."""
    now = now_dt()
    if now.hour < COMPILE_AFTER_HOUR:
        return

    today_log = f"{now.strftime('%Y-%m-%d')}.md"
    compile_state_file = SCRIPTS_DIR / "state.json"

    if compile_state_file.exists():
        try:
            compile_state = json.loads(compile_state_file.read_text(encoding="utf-8"))
            ingested = compile_state.get("ingested", {})
            if today_log in ingested:
                from hashlib import sha256

                log_path = DAILY_DIR / today_log
                if log_path.exists():
                    current_hash = sha256(log_path.read_bytes()).hexdigest()[:16]
                    if ingested[today_log].get("hash") == current_hash:
                        return
        except (json.JSONDecodeError, OSError):
            pass

    logging.info("Auto compile trigger fired (after %d:00)", COMPILE_AFTER_HOUR)
    cmd = [sys.executable, str(SCRIPT_DIR / "compile.py")]
    kwargs: dict[str, object] = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    else:
        kwargs["start_new_session"] = True

    try:
        compile_log = open(str(SCRIPTS_DIR / "compile.log"), "a", encoding="utf-8")
        subprocess.Popen(cmd, stdout=compile_log, stderr=subprocess.STDOUT, cwd=str(SCRIPT_DIR.parent), **kwargs)
    except Exception as exc:
        logging.error("Failed to spawn compile.py: %s", exc)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest conversation context into daily logs")
    parser.add_argument("context_file", help="Path to markdown context file")
    parser.add_argument("session_id", help="Session identifier")
    parser.add_argument("--title", help="Human title for the session entry")
    parser.add_argument(
        "--source-type",
        default="note",
        choices=SOURCE_TYPES,
        help="Structured source classification for the entry",
    )
    parser.add_argument("--workspace", help="Workspace path associated with the session")
    parser.add_argument("--repo", help="Repository identifier associated with the session")
    parser.add_argument("--task-ref", help="Task or ticket reference associated with the session")
    parser.add_argument(
        "--no-compile-trigger",
        action="store_true",
        help="Disable automatic post-6PM compile trigger",
    )
    args = parser.parse_args()

    context_file = Path(args.context_file)
    logging.info("flush.py started for session %s, context: %s", args.session_id, context_file)

    if not context_file.exists():
        logging.error("Context file not found: %s", context_file)
        return

    state = load_flush_state()
    if state.get("session_id") == args.session_id and time.time() - state.get("timestamp", 0) < 60:
        logging.info("Skipping duplicate flush for session %s", args.session_id)
        cleanup_context_file(context_file)
        return

    context = context_file.read_text(encoding="utf-8").strip()
    if not context:
        logging.info("Context file is empty, skipping")
        cleanup_context_file(context_file)
        return

    structured, resolved_title = build_structured_entry(
        context,
        session_id=args.session_id,
        title=args.title,
        source_type=args.source_type,
        workspace=args.workspace,
        repo=args.repo,
        task_ref=args.task_ref,
    )
    append_to_daily_log(structured, resolved_title)

    save_flush_state({"session_id": args.session_id, "timestamp": time.time()})
    cleanup_context_file(context_file)

    if not args.no_compile_trigger:
        maybe_trigger_compilation()

    logging.info("Flush complete for session %s", args.session_id)


if __name__ == "__main__":
    main()
