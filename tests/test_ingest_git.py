from __future__ import annotations

import subprocess
from pathlib import Path

from tests.support import KBScriptTestCase


class IngestGitCLITest(KBScriptTestCase):
    def run_git(self, repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            check=True,
        )

    def commit_file(self, repo: Path, path: str, content: str, message: str) -> None:
        target = repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        self.run_git(repo, "add", path)
        self.run_git(repo, "commit", "-m", message)

    def make_repo(self) -> Path:
        workspace_root = self.kb_root / "workspace"
        workspace_root.mkdir()
        self.run_git(workspace_root, "init")
        self.run_git(workspace_root, "config", "user.email", "test@example.com")
        self.run_git(workspace_root, "config", "user.name", "Test User")
        self.commit_file(workspace_root, "README.md", "# Test repo\n", "Initial commit")
        self.commit_file(workspace_root, "src/app.py", "print('hello')\n", "Add app entrypoint")
        self.commit_file(workspace_root, "docs/plan.md", "# Plan\n", "Document memory plan")
        return workspace_root

    def test_ingest_git_imports_requested_commit_range(self) -> None:
        workspace_root = self.make_repo()

        result = self.run_package_cli(
            "ingest-git",
            "--since",
            "HEAD~2",
            "--no-compile",
            "--no-compile-trigger",
            now="2026-04-12T10:00:00-05:00",
            cwd=workspace_root,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Imported 2 git commit(s) from HEAD~2..HEAD.", result.stdout)

        daily_path = workspace_root / ".codex-memory" / "daily" / "2026-04-12.md"
        daily_text = daily_path.read_text(encoding="utf-8")
        self.assertIn("**Source Type:** commit-summary", daily_text)
        self.assertIn("**Workspace:**", daily_text)
        self.assertIn("**Repo:** workspace", daily_text)
        self.assertIn("**Task Ref:** git:HEAD~2..HEAD", daily_text)
        self.assertIn("Imported 2 commit(s) from git range HEAD~2..HEAD.", daily_text)
        self.assertIn("Add app entrypoint", daily_text)
        self.assertIn("Document memory plan", daily_text)
        self.assertIn("- src/app.py", daily_text)
        self.assertIn("- docs/plan.md", daily_text)
        self.assertNotIn("- README.md", daily_text)

    def test_ingest_git_no_commits_is_readable_noop(self) -> None:
        workspace_root = self.make_repo()

        result = self.run_package_cli(
            "ingest-git",
            "--since",
            "HEAD",
            "--no-compile",
            "--no-compile-trigger",
            now="2026-04-12T10:05:00-05:00",
            cwd=workspace_root,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("No git commits found for range HEAD..HEAD.", result.stdout)
        self.assertFalse(
            (workspace_root / ".codex-memory" / "daily" / "2026-04-12.md").exists()
        )
