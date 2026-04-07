"""Optional Codex session-stop helper.

Flushes a prepared context file into daily logs.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ROOT / "scripts"


def main() -> None:
    parser = argparse.ArgumentParser(description="Flush a codex session context file")
    parser.add_argument("--context-file", required=True, help="Markdown context file")
    parser.add_argument("--session-id", required=True, help="Session id for dedupe")
    parser.add_argument("--no-compile-trigger", action="store_true")
    args = parser.parse_args()

    cmd = [
        sys.executable,
        str(SCRIPTS_DIR / "flush.py"),
        args.context_file,
        args.session_id,
    ]
    if args.no_compile_trigger:
        cmd.append("--no-compile-trigger")

    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
