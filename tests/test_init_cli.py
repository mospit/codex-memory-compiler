from __future__ import annotations

import json
import os
import subprocess
import sys

from tests.support import KBScriptTestCase, REPO_ROOT, SCRIPT_DIR


class InitCLITest(KBScriptTestCase):
    def test_init_creates_workspace_scaffold_and_supports_followup_ingest(self) -> None:
        workspace_root = self.kb_root / "workspace"
        workspace_root.mkdir()

        init_result = self.run_script(
            "init.py",
            "--workspace-root",
            str(workspace_root),
            now="2026-04-10T12:00:00-05:00",
        )

        self.assertEqual(init_result.returncode, 0, init_result.stderr)

        memory_root = workspace_root / ".codex-memory"
        self.assertTrue((memory_root / "daily").is_dir())
        self.assertTrue((memory_root / "knowledge" / "concepts").is_dir())
        self.assertTrue((memory_root / "knowledge" / "connections").is_dir())
        self.assertTrue((memory_root / "knowledge" / "qa").is_dir())
        self.assertTrue((memory_root / "reports").is_dir())
        self.assertTrue((memory_root / "scripts").is_dir())

        index_text = (memory_root / "knowledge" / "index.md").read_text(encoding="utf-8")
        log_text = (memory_root / "knowledge" / "log.md").read_text(encoding="utf-8")
        readme_text = (memory_root / "README.md").read_text(encoding="utf-8")
        state = json.loads((memory_root / "scripts" / "state.json").read_text(encoding="utf-8"))

        self.assertIn("# Knowledge Base Index", index_text)
        self.assertEqual(log_text, "# Build Log\n\n")
        self.assertIn("Set `KB_ROOT_DIR` to this folder", readme_text)
        self.assertEqual(state["ingested"], {})
        self.assertIn(f'$env:KB_ROOT_DIR = "{memory_root.as_posix()}"', init_result.stdout)

        env = os.environ.copy()
        env["KB_ROOT_DIR"] = str(memory_root)
        env["KB_NOW"] = "2026-04-10T12:05:00-05:00"
        pythonpath = env.get("PYTHONPATH")
        env["PYTHONPATH"] = f"{REPO_ROOT}{os.pathsep}{pythonpath}" if pythonpath else str(REPO_ROOT)

        ingest_result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_DIR / "ingest.py"),
                "--text",
                "Initialized memory compiler for a new project.",
                "--title",
                "Memory Setup",
                "--source-type",
                "codex-summary",
                "--workspace",
                str(workspace_root),
                "--no-compile-trigger",
            ],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(ingest_result.returncode, 0, ingest_result.stderr)
        self.assertTrue((memory_root / "daily" / "2026-04-10.md").exists())
