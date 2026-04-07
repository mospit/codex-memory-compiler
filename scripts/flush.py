"""Memory ingest/flush utility for conversation context.

This script is hook-agnostic and can be used manually from Codex app workflows
or from optional external hook integrations.

Usage:
    uv run python scripts/flush.py <context_file.md> <session_id>
    uv run python scripts/flush.py <context_file.md> <session_id> --no-compile-trigger
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from config import CODE_SCRIPTS_DIR, DAILY_DIR, ROOT_DIR, SCRIPTS_DIR

STATE_FILE = SCRIPTS_DIR / "last-flush.json"
LOG_FILE = SCRIPTS_DIR / "flush.log"

logging.basicConfig(
    filename=str(LOG_FILE),
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

COMPILE_AFTER_HOUR = 18  # 6 PM local time
MAX_EXCHANGES = 10


def load_flush_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_flush_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state), encoding="utf-8")


def cleanup_context_file(path: Path) -> None:
    """Delete ephemeral context files created by ingest helpers."""
    if ".tmp" in path.parts:
        path.unlink(missing_ok=True)


def append_to_daily_log(content: str, section: str = "Session") -> None:
    """Append content to today's daily log."""
    today = datetime.now(timezone.utc).astimezone()
    log_path = DAILY_DIR / f"{today.strftime('%Y-%m-%d')}.md"

    if not log_path.exists():
        DAILY_DIR.mkdir(parents=True, exist_ok=True)
        log_path.write_text(
            f"# Daily Log: {today.strftime('%Y-%m-%d')}\n\n## Sessions\n\n## Memory Maintenance\n\n",
            encoding="utf-8",
        )

    time_str = today.strftime("%H:%M")
    entry = f"### {section} ({time_str})\n\n{content}\n\n"

    with open(log_path, "a", encoding="utf-8") as f:
        f.write(entry)


def parse_dialogue_lines(context: str) -> tuple[list[str], list[str]]:
    """Extract user/assistant lines from markdown context."""
    user_lines: list[str] = []
    assistant_lines: list[str] = []

    for raw in context.splitlines():
        line = raw.strip()
        if not line:
            continue
        user_match = re.match(r"^\*\*User:\*\*\s*(.+)$", line, flags=re.IGNORECASE)
        if user_match:
            user_lines.append(user_match.group(1).strip())
            continue

        assistant_match = re.match(r"^\*\*Assistant:\*\*\s*(.+)$", line, flags=re.IGNORECASE)
        if assistant_match:
            assistant_lines.append(assistant_match.group(1).strip())

    return user_lines, assistant_lines


def trim_sentence(text: str, max_chars: int = 220) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def build_structured_entry(context: str) -> str:
    """Create deterministic structured daily-log content from context."""
    user_lines, assistant_lines = parse_dialogue_lines(context)

    context_line = (
        trim_sentence(user_lines[0])
        if user_lines
        else "No explicit user objective found in captured context."
    )

    exchanges = []
    for i in range(min(MAX_EXCHANGES, max(len(user_lines), len(assistant_lines)))):
        q = user_lines[i] if i < len(user_lines) else "(no user line captured)"
        a = assistant_lines[i] if i < len(assistant_lines) else "(no assistant line captured)"
        exchanges.append(f"- User: {trim_sentence(q, 160)}")
        exchanges.append(f"  Assistant: {trim_sentence(a, 180)}")

    decisions = []
    lessons = []
    actions = []

    candidate_lines = user_lines + assistant_lines
    decision_terms = ("decide", "chose", "choose", "use", "adopt", "migrate", "switch")
    lesson_terms = ("learned", "gotcha", "issue", "failed", "error", "bug", "note")
    action_terms = ("todo", "follow up", "next", "later", "action", "plan")

    for line in candidate_lines:
        lower = line.lower()
        if any(t in lower for t in decision_terms) and len(decisions) < 4:
            decisions.append(f"- {trim_sentence(line, 180)}")
        if any(t in lower for t in lesson_terms) and len(lessons) < 4:
            lessons.append(f"- {trim_sentence(line, 180)}")
        if any(t in lower for t in action_terms) and len(actions) < 4:
            actions.append(f"- [ ] {trim_sentence(line, 160)}")

    parts = [f"**Context:** {context_line}", "", "**Key Exchanges:**"]
    parts.extend(exchanges if exchanges else ["- No salient exchanges parsed."])

    if decisions:
        parts.extend(["", "**Decisions Made:**", *decisions])
    if lessons:
        parts.extend(["", "**Lessons Learned:**", *lessons])
    if actions:
        parts.extend(["", "**Action Items:**", *actions])

    return "\n".join(parts)


def maybe_trigger_compilation() -> None:
    """If it's past compile hour and today's log changed, run compile.py."""
    now = datetime.now(timezone.utc).astimezone()
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

    compile_script = CODE_SCRIPTS_DIR / "compile.py"
    if not compile_script.exists():
        return

    logging.info("Auto compile trigger fired (after %d:00)", COMPILE_AFTER_HOUR)
    cmd = [sys.executable, str(compile_script)]
    kwargs: dict = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    else:
        kwargs["start_new_session"] = True

    try:
        log_handle = open(str(SCRIPTS_DIR / "compile.log"), "a", encoding="utf-8")
        subprocess.Popen(cmd, stdout=log_handle, stderr=subprocess.STDOUT, cwd=str(ROOT_DIR), **kwargs)
    except Exception as exc:
        logging.error("Failed to spawn compile.py: %s", exc)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest conversation context into daily logs")
    parser.add_argument("context_file", help="Path to markdown context file")
    parser.add_argument("session_id", help="Session identifier")
    parser.add_argument(
        "--no-compile-trigger",
        action="store_true",
        help="Disable automatic post-6PM compile trigger",
    )
    args = parser.parse_args()

    context_file = Path(args.context_file)
    session_id = args.session_id

    logging.info("flush.py started for session %s, context: %s", session_id, context_file)

    if not context_file.exists():
        logging.error("Context file not found: %s", context_file)
        return

    state = load_flush_state()
    if state.get("session_id") == session_id and time.time() - state.get("timestamp", 0) < 60:
        logging.info("Skipping duplicate flush for session %s", session_id)
        cleanup_context_file(context_file)
        return

    context = context_file.read_text(encoding="utf-8").strip()
    if not context:
        logging.info("Context file is empty, skipping")
        cleanup_context_file(context_file)
        return

    logging.info("Flushing session %s: %d chars", session_id, len(context))

    structured = build_structured_entry(context)
    append_to_daily_log(structured, "Session")

    save_flush_state({"session_id": session_id, "timestamp": time.time()})
    cleanup_context_file(context_file)

    if not args.no_compile_trigger:
        maybe_trigger_compilation()

    logging.info("Flush complete for session %s", session_id)


if __name__ == "__main__":
    main()
