"""Optional Codex session-start helper.

Creates an editable markdown context template for deterministic ingestion.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ROOT / "scripts"


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a codex session context template")
    parser.add_argument("--session-id", default="", help="Session id used in output filename")
    args = parser.parse_args()

    session_id = args.session_id or datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    out_dir = SCRIPTS_DIR / ".tmp"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"session-{session_id}.md"

    if not out_file.exists():
        out_file.write_text(
            "**User:** <what I worked on>\n"
            "**Assistant:** <important response or summary>\n",
            encoding="utf-8",
        )

    print(out_file)


if __name__ == "__main__":
    main()
