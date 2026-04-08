"""Manual ingest entry point for Codex app workflows."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from config import now_dt

SCRIPT_DIR = Path(__file__).resolve().parent
TMP_DIR = SCRIPT_DIR / ".tmp"
SOURCE_TYPES = ("note", "codex-summary", "commit-summary", "pr-summary")


def build_context_from_text(text: str, source_type: str) -> str:
    assistant_line = f"Captured via {source_type} ingest workflow."
    return f"**User:** {text}\n**Assistant:** {assistant_line}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Manual ingest helper")
    parser.add_argument("--text", help="Short free-form session summary")
    parser.add_argument("--file", help="Path to markdown context file")
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
    parser.add_argument(
        "--no-compile-trigger",
        action="store_true",
        help="Disable automatic post-6PM compile trigger",
    )
    args = parser.parse_args()

    if not args.text and not args.file:
        raise SystemExit("Provide either --text or --file")

    if args.file:
        context_path = Path(args.file)
        if not context_path.exists():
            raise SystemExit(f"Context file not found: {args.file}")
    else:
        TMP_DIR.mkdir(parents=True, exist_ok=True)
        context_path = TMP_DIR / f"ingest-{args.session_id}.md"
        context_path.write_text(
            build_context_from_text(args.text or "", args.source_type),
            encoding="utf-8",
        )

    cmd = [
        sys.executable,
        str(SCRIPT_DIR / "flush.py"),
        str(context_path),
        args.session_id,
        "--source-type",
        args.source_type,
    ]
    if args.title:
        cmd.extend(["--title", args.title])
    if args.workspace:
        cmd.extend(["--workspace", args.workspace])
    if args.repo:
        cmd.extend(["--repo", args.repo])
    if args.task_ref:
        cmd.extend(["--task-ref", args.task_ref])
    if args.no_compile_trigger:
        cmd.append("--no-compile-trigger")

    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
