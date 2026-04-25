from __future__ import annotations

from pathlib import Path

from tests.support import KBScriptTestCase


class GlobalCLITest(KBScriptTestCase):
    def test_module_entry_help_is_read_only(self) -> None:
        workspace_root = self.kb_root / "workspace"
        workspace_root.mkdir()

        result = self.run_package_cli("--help", now="2026-04-12T08:00:00-05:00", cwd=workspace_root)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("usage: codex-memory", result.stdout)
        self.assertFalse((workspace_root / ".codex-memory").exists())

    def test_init_creates_workspace_scaffold_via_module_entry(self) -> None:
        workspace_root = self.kb_root / "workspace"
        workspace_root.mkdir()

        result = self.run_package_cli(
            "init",
            "--workspace-root",
            str(workspace_root),
            now="2026-04-12T09:00:00-05:00",
            cwd=workspace_root,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        memory_root = workspace_root / ".codex-memory"
        self.assertTrue((memory_root / "daily").is_dir())
        self.assertTrue((memory_root / "knowledge" / "concepts").is_dir())
        self.assertTrue((memory_root / "knowledge" / "connections").is_dir())
        self.assertTrue((memory_root / "knowledge" / "qa").is_dir())
        self.assertTrue((memory_root / "reports").is_dir())
        self.assertTrue((memory_root / "scripts").is_dir())

        readme_text = (memory_root / "README.md").read_text(encoding="utf-8")
        self.assertIn("codex-memory ingest", readme_text)
        self.assertIn(f'$env:KB_ROOT_DIR = "{memory_root.as_posix()}"', result.stdout)

    def test_ingest_auto_creates_cwd_memory_root(self) -> None:
        workspace_root = self.kb_root / "workspace"
        workspace_root.mkdir()

        result = self.run_package_cli(
            "ingest",
            "--text",
            "Initialized global CLI memory compiler support.",
            "--title",
            "Memory Setup",
            "--source-type",
            "codex-summary",
            "--no-compile-trigger",
            now="2026-04-12T09:05:00-05:00",
            cwd=workspace_root,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        daily_text = (workspace_root / ".codex-memory" / "daily" / "2026-04-12.md").read_text(encoding="utf-8")
        self.assertIn("**Title:** Memory Setup", daily_text)
        self.assertIn("**Source Type:** codex-summary", daily_text)

    def test_compile_and_lint_auto_create_empty_scaffold(self) -> None:
        workspace_root = self.kb_root / "workspace"
        workspace_root.mkdir()

        compile_result = self.run_package_cli(
            "compile",
            now="2026-04-12T09:10:00-05:00",
            cwd=workspace_root,
        )
        self.assertEqual(compile_result.returncode, 0, compile_result.stderr)
        self.assertIn("Nothing to compile", compile_result.stdout)

        lint_result = self.run_package_cli(
            "lint",
            "--structural-only",
            now="2026-04-12T09:15:00-05:00",
            cwd=workspace_root,
        )
        self.assertEqual(lint_result.returncode, 0, lint_result.stderr)
        report_path = workspace_root / ".codex-memory" / "reports" / "lint-2026-04-12.md"
        self.assertTrue(report_path.exists())
        self.assertIn("All checks passed", report_path.read_text(encoding="utf-8"))

    def test_query_without_existing_root_fails_cleanly(self) -> None:
        workspace_root = self.kb_root / "workspace"
        workspace_root.mkdir()

        result = self.run_package_cli(
            "query",
            "What did I work on?",
            now="2026-04-12T09:20:00-05:00",
            cwd=workspace_root,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Memory root not found", result.stderr)
        self.assertFalse((workspace_root / ".codex-memory").exists())

    def test_target_precedence_root_then_workspace_then_env(self) -> None:
        workspace_root = self.kb_root / "workspace"
        workspace_root.mkdir()
        env_root = self.kb_root / "env-memory"
        explicit_root = self.kb_root / "explicit-memory"

        root_result = self.run_package_cli(
            "ingest",
            "--root",
            str(explicit_root),
            "--workspace-root",
            str(workspace_root),
            "--text",
            "Root flag should win.",
            "--source-type",
            "codex-summary",
            "--no-compile-trigger",
            now="2026-04-12T09:25:00-05:00",
            cwd=self.kb_root,
            extra_env={"KB_ROOT_DIR": str(env_root)},
        )
        self.assertEqual(root_result.returncode, 0, root_result.stderr)
        self.assertTrue((explicit_root / "daily" / "2026-04-12.md").exists())
        self.assertFalse(env_root.exists())
        self.assertFalse((workspace_root / ".codex-memory").exists())

        workspace_result = self.run_package_cli(
            "ingest",
            "--workspace-root",
            str(workspace_root),
            "--text",
            "Workspace flag should beat env.",
            "--source-type",
            "codex-summary",
            "--no-compile-trigger",
            now="2026-04-12T09:30:00-05:00",
            cwd=self.kb_root,
            extra_env={"KB_ROOT_DIR": str(env_root)},
        )
        self.assertEqual(workspace_result.returncode, 0, workspace_result.stderr)
        self.assertTrue((workspace_root / ".codex-memory" / "daily" / "2026-04-12.md").exists())
        self.assertFalse(env_root.exists())

        env_result = self.run_package_cli(
            "ingest",
            "--text",
            "Env root should beat cwd default.",
            "--source-type",
            "codex-summary",
            "--no-compile-trigger",
            now="2026-04-12T09:35:00-05:00",
            cwd=self.kb_root,
            extra_env={"KB_ROOT_DIR": str(env_root)},
        )
        self.assertEqual(env_result.returncode, 0, env_result.stderr)
        self.assertTrue((env_root / "daily" / "2026-04-12.md").exists())

    def test_query_handles_bom_content_without_console_crash(self) -> None:
        workspace_root = self.kb_root / "workspace"
        memory_root = workspace_root / ".codex-memory"
        concept_dir = memory_root / "knowledge" / "concepts"
        concept_dir.mkdir(parents=True)
        (memory_root / "knowledge" / "connections").mkdir(parents=True)
        (memory_root / "knowledge" / "qa").mkdir(parents=True)
        (memory_root / "reports").mkdir(parents=True)
        (memory_root / "scripts").mkdir(parents=True)
        (memory_root / "scripts" / "state.json").write_text(
            '{"ingested": {}, "last_lint": null, "query_count": 0, "total_cost": 0.0}',
            encoding="utf-8",
        )
        article_path = concept_dir / "bom-note.md"
        article_path.write_text(
            "\n".join(
                [
                    "---",
                    'managed_by: "codex-memory-compiler"',
                    'title: "BOM Note"',
                    'summary: "\ufeffBOM-safe summary for query output."',
                    'keywords:',
                    '  - "bom"',
                    '  - "query"',
                    'updated: "2026-04-12"',
                    "---",
                    "",
                    "# BOM Note",
                    "",
                    "BOM-safe summary for query output.",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        (memory_root / "knowledge" / "index.md").write_text(
            "\n".join(
                [
                    "# Knowledge Base Index",
                    "",
                    "| Article | Type | Summary | Keywords | Sources | Updated |",
                    "|---------|------|---------|----------|---------|---------|",
                    "| [[concepts/bom-note]] | concept | \ufeffBOM-safe summary for query output. | bom, query | (none) | 2026-04-12 |",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        (memory_root / "knowledge" / "log.md").write_text("# Build Log\n\n", encoding="utf-8")

        result = self.run_package_cli(
            "query",
            "bom query output",
            "--explain",
            now="2026-04-12T09:40:00-05:00",
            cwd=workspace_root,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Confidence:", result.stdout)
        self.assertIn("[[concepts/bom-note]]", result.stdout)
