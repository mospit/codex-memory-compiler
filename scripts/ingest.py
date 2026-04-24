"""Manual ingest entry point for Codex app workflows."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

from config import now_dt

SCRIPT_DIR = Path(__file__).resolve().parent
TMP_DIR = SCRIPT_DIR / ".tmp"
SOURCE_TYPES = ("note", "codex-summary", "commit-summary", "pr-summary", "codex-chat")
STRUCTURED_HEADING_PATTERN = re.compile(
    r"(?m)^##\s+(Goal|Summary|Current Status|Decisions|Decision Links|Blockers|Files|Validation|Verification State|Evidence|Next Steps|Open Questions|Date Context)\s*$"
)


def build_context_from_text(text: str, source_type: str) -> str:
    if STRUCTURED_HEADING_PATTERN.search(text):
        return text.strip()
    assistant_line = f"Captured via {source_type} ingest workflow."
    return f"**User:** {text}\n**Assistant:** {assistant_line}"


def append_section(lines: list[str], heading: str, items: list[str], *, checkbox: bool = False) -> None:
    """Append a structured markdown section when items are present."""
    cleaned = [item.strip() for item in items if item and item.strip()]
    if not cleaned:
        return
    if lines:
        lines.append("")
    lines.append(f"## {heading}")
    prefix = "- [ ] " if checkbox else "- "
    lines.extend(f"{prefix}{item}" for item in cleaned)


def has_structured_flag_content(args: argparse.Namespace) -> bool:
    """Return whether structured section flags provide ingest content."""
    return any(
        [
            bool((args.goal or "").strip()),
            bool((args.current_status or "").strip()),
            bool(args.decision),
            bool(args.decision_link),
            bool(args.blocker),
            bool(args.file_touched),
            bool(args.validation),
            bool((args.verification_state or "").strip()),
            bool(args.evidence),
            bool(args.next_step),
            bool(args.open_question),
        ]
    )


def build_context_from_cli_flags(args: argparse.Namespace) -> str:
    """Build a structured markdown recap from CLI section flags."""
    lines: list[str] = []
    if (args.goal or "").strip():
        append_section(lines, "Goal", [args.goal.strip()])

    summary_lines = []
    if (args.text or "").strip():
        summary_lines.append(args.text.strip())
    elif (args.current_status or "").strip():
        summary_lines.append(args.current_status.strip())
    elif (args.goal or "").strip():
        summary_lines.append(args.goal.strip())
    append_section(lines, "Summary", summary_lines)

    if (args.current_status or "").strip():
        append_section(lines, "Current Status", [args.current_status.strip()])
    append_section(lines, "Decisions", args.decision or [])
    append_section(lines, "Decision Links", args.decision_link or [])
    append_section(lines, "Blockers", args.blocker or [])
    append_section(lines, "Files", args.file_touched or [])
    append_section(lines, "Validation", args.validation or [])
    if (args.verification_state or "").strip():
        append_section(lines, "Verification State", [args.verification_state.strip()])
    append_section(lines, "Evidence", args.evidence or [])
    append_section(lines, "Next Steps", args.next_step or [], checkbox=False)
    append_section(lines, "Open Questions", args.open_question or [])
    return "\n".join(lines).strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="Manual ingest helper")
    parser.add_argument("--text", help="Short free-form session summary")
    parser.add_argument("--file", help="Path to markdown context file")
    parser.add_argument(
        "--codex-chat-file",
        help="Path to an exported Codex markdown conversation file",
    )
    parser.add_argument(
        "--session-id",
        default=f"manual-{now_dt().strftime('%Y%m%d%H%M%S')}",
        help="Session id for deduplication tracking",
    )
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
    parser.add_argument("--goal", help="Goal statement for a structured implementation batch")
    parser.add_argument("--current-status", help="Current status summary for a structured implementation batch")
    parser.add_argument("--decision", action="append", default=[], help="Repeatable explicit decision item")
    parser.add_argument("--decision-link", action="append", default=[], help="Repeatable decision relation such as 'supersedes: [[decisions/foo]]'")
    parser.add_argument("--blocker", action="append", default=[], help="Repeatable blocker item")
    parser.add_argument("--file-touched", action="append", default=[], help="Repeatable file path anchor")
    parser.add_argument("--validation", action="append", default=[], help="Repeatable validation command or check")
    parser.add_argument("--verification-state", help="Verification state summary")
    parser.add_argument("--evidence", action="append", default=[], help="Repeatable evidence excerpt")
    parser.add_argument("--next-step", action="append", default=[], help="Repeatable next-step item")
    parser.add_argument("--open-question", action="append", default=[], help="Repeatable open question")
    parser.add_argument(
        "--compile",
        dest="compile",
        action="store_true",
        default=None,
        help="Run compile.py after ingest (default behavior).",
    )
    parser.add_argument(
        "--no-compile",
        dest="compile",
        action="store_false",
        default=None,
        help="Skip compile.py after ingest.",
    )
    parser.add_argument(
        "--lint",
        dest="lint",
        action="store_true",
        default=None,
        help="Run lint.py --autofix after ingest (default behavior).",
    )
    parser.add_argument(
        "--no-lint",
        dest="lint",
        action="store_false",
        default=None,
        help="Skip lint.py --autofix after ingest.",
    )
    parser.add_argument(
        "--no-compile-trigger",
        action="store_true",
        help="Disable automatic post-6PM compile trigger",
    )
    args = parser.parse_args()

    has_structured_flags = has_structured_flag_content(args)
    if args.text and (args.file or args.codex_chat_file):
        raise SystemExit("Provide only one of --text, --file, or --codex-chat-file")
    if args.file and args.codex_chat_file:
        raise SystemExit("Provide only one of --file or --codex-chat-file")
    if (args.file or args.codex_chat_file) and has_structured_flags:
        raise SystemExit("Structured section flags are supported only with --text or as a flag-only structured ingest.")
    if not args.text and not args.file and not args.codex_chat_file and not has_structured_flags:
        raise SystemExit(
            "Provide one of --text, --file, or --codex-chat-file, or use structured section flags like --goal/--current-status."
        )

    compile_enabled = True if args.compile is None else args.compile
    lint_enabled = True if args.lint is None else args.lint
    if not compile_enabled:
        if args.lint is True:
            raise SystemExit("Cannot lint when compile is disabled. Remove --lint or add --no-lint.")
        lint_enabled = False

    source_type = args.source_type
    if args.codex_chat_file:
        source_type = "codex-chat"

    if args.file or args.codex_chat_file:
        source_path = args.codex_chat_file or args.file
        assert source_path is not None
        context_path = Path(source_path)
        if not context_path.exists():
            raise SystemExit(f"Context file not found: {source_path}")
    else:
        TMP_DIR.mkdir(parents=True, exist_ok=True)
        context_path = TMP_DIR / f"ingest-{args.session_id}.md"
        context_text = build_context_from_cli_flags(args) if has_structured_flags else build_context_from_text(args.text or "", source_type)
        context_path.write_text(
            context_text,
            encoding="utf-8",
        )

    cmd = [
        sys.executable,
        str(SCRIPT_DIR / "flush.py"),
        str(context_path),
        args.session_id,
        "--source-type",
        source_type,
    ]
    if args.title:
        cmd.extend(["--title", args.title])
    if args.workspace:
        cmd.extend(["--workspace", args.workspace])
    if args.repo:
        cmd.extend(["--repo", args.repo])
    if args.task_ref:
        cmd.extend(["--task-ref", args.task_ref])
    if args.no_compile_trigger or compile_enabled:
        cmd.append("--no-compile-trigger")

    subprocess.run(cmd, check=True)

    if compile_enabled:
        subprocess.run([sys.executable, str(SCRIPT_DIR / "compile.py")], check=True)
    if lint_enabled:
        subprocess.run([sys.executable, str(SCRIPT_DIR / "lint.py"), "--autofix"], check=True)


if __name__ == "__main__":
    main()
