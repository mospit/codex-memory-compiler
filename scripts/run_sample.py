"""Run the deterministic memory pipeline against sample fixtures in an isolated workspace."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAMPLE_CONTEXT_DIR = ROOT / "sample" / "demo-context"


def run(cmd: list[str], env: dict[str, str]) -> None:
    subprocess.run(cmd, check=True, cwd=ROOT, env=env)


def main() -> None:
    if not SAMPLE_CONTEXT_DIR.exists():
        raise SystemExit(f"Sample context directory not found: {SAMPLE_CONTEXT_DIR}")

    workspace = Path(tempfile.mkdtemp(prefix="memory-compiler-sample-"))
    for directory in ("daily", "knowledge/concepts", "knowledge/connections", "knowledge/qa", "reports", "scripts"):
        (workspace / directory).mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["MEMORY_COMPILER_ROOT"] = str(workspace)

    for fixture in sorted(SAMPLE_CONTEXT_DIR.glob("*.md")):
        session_id = f"sample-{fixture.stem}"
        run([sys.executable, "scripts/ingest.py", "--file", str(fixture), "--session-id", session_id, "--no-compile-trigger"], env)

    run([sys.executable, "scripts/compile.py"], env)
    run([sys.executable, "scripts/query.py", "What did I decide about auth migration?"], env)
    run([sys.executable, "scripts/lint.py", "--structural-only"], env)

    print(f"Sample pipeline completed in isolated workspace: {workspace}")


if __name__ == "__main__":
    main()
