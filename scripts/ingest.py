"""Manual ingest entry point for Codex app workflows.

Usage:
    uv run python scripts/ingest.py --text "Worked on lint false positives"
    uv run python scripts/ingest.py --file notes/session.md --session-id codex-manual-001
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from config import CODE_SCRIPTS_DIR, SCRIPTS_DIR

TMP_DIR = SCRIPTS_DIR / ".tmp"


def build_context_from_text(text: str) -> str:
    return f"**User:** {text}\n**Assistant:** Captured via manual ingest workflow."


def main() -> None:
    parser = argparse.ArgumentParser(description="Manual ingest helper")
    parser.add_argument("--text", help="Short free-form session summary")
    parser.add_argument("--file", help="Path to markdown context file")
    parser.add_argument(
        "--session-id",
        default=f"manual-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        help="Session id for deduplication tracking",
    )
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
        context_path.write_text(build_context_from_text(args.text or ""), encoding="utf-8")

    cmd = [
        sys.executable,
        str(CODE_SCRIPTS_DIR / "flush.py"),
        str(context_path),
        args.session_id,
    ]
    if args.no_compile_trigger:
        cmd.append("--no-compile-trigger")

    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
