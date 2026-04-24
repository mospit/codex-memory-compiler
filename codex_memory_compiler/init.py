"""Initialize a reusable memory-root scaffold for a workspace."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from .utils import ensure_memory_root_scaffold

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent


def resolve_root(args: argparse.Namespace) -> tuple[Path, Path | None]:
    """Resolve the memory root and optional workspace root from CLI args."""
    workspace_root = Path(args.workspace_root).expanduser().resolve() if args.workspace_root else None
    if workspace_root and not workspace_root.exists():
        raise SystemExit(f"Workspace root not found: {workspace_root}")
    if workspace_root and not workspace_root.is_dir():
        raise SystemExit(f"Workspace root is not a directory: {workspace_root}")

    if args.root:
        root_dir = Path(args.root).expanduser().resolve()
    elif workspace_root:
        root_dir = (workspace_root / ".codex-memory").resolve()
    else:
        root_dir = Path(os.getenv("KB_ROOT_DIR", REPO_ROOT)).expanduser().resolve()

    if root_dir.exists() and not root_dir.is_dir():
        raise SystemExit(f"Memory root is not a directory: {root_dir}")

    return root_dir, workspace_root


def render_readme(root_dir: Path, workspace_root: Path | None) -> str:
    """Render a lightweight guide for the initialized memory root."""
    lines = [
        "# Codex Memory Root",
        "",
        "This folder stores the Codex Memory Compiler data for a workspace.",
        "",
        "## Layout",
        "",
        "- `daily/` append-only source logs",
        "- `knowledge/` compiled concepts, connections, and filed Q&A",
        "- `reports/` lint and maintenance reports",
        "- `scripts/state.json` local compiler state",
        "",
        "## Use This Root",
        "",
        "Set `KB_ROOT_DIR` to this folder before running the compiler scripts.",
        "",
        "```powershell",
        f'$env:KB_ROOT_DIR = "{root_dir.as_posix()}"',
        "```",
        "",
        "Then run the installed CLI from that workspace:",
        "",
        "```powershell",
        'codex-memory ingest --text "Session summary" --source-type codex-summary',
        "codex-memory compile",
        'codex-memory query "What did I work on?" --explain',
        "```",
        "",
        "## Obsidian",
        "",
        "Open this folder as the vault root. Do not point Obsidian only at `knowledge/`.",
    ]
    if workspace_root:
        lines.extend(
            [
                "",
                "## Workspace",
                "",
                f"- Workspace root: `{workspace_root.as_posix()}`",
            ]
        )
    lines.append("")
    return "\n".join(lines)


def maybe_write_readme(root_dir: Path, workspace_root: Path | None) -> Path | None:
    """Create a root README when one does not already exist."""
    readme_path = root_dir / "README.md"
    if readme_path.exists():
        return None
    readme_path.write_text(render_readme(root_dir, workspace_root), encoding="utf-8")
    return readme_path


def main(
    argv: list[str] | None = None,
    *,
    root_dir: Path | None = None,
    workspace_root: Path | None = None,
) -> int:
    if root_dir is None:
        parser = argparse.ArgumentParser(description="Initialize a Codex memory root scaffold")
        parser.add_argument("--root", help="Explicit memory root path to initialize")
        parser.add_argument(
            "--workspace-root",
            help="Workspace that should use the memory root; defaults to <workspace-root>/.codex-memory",
        )
        args = parser.parse_args(argv)
        root_dir, workspace_root = resolve_root(args)

    paths = ensure_memory_root_scaffold(root_dir)
    readme_path = maybe_write_readme(root_dir, workspace_root)

    print(f"Initialized memory root: {paths['root_dir'].as_posix()}")
    print("Created or verified:")
    print(f"  - {paths['daily_dir'].as_posix()}")
    print(f"  - {paths['knowledge_dir'].as_posix()}")
    print(f"  - {paths['reports_dir'].as_posix()}")
    print(f"  - {paths['scripts_dir'].as_posix()}")
    print("")
    print("Use in this PowerShell session:")
    print(f'  $env:KB_ROOT_DIR = "{paths["root_dir"].as_posix()}"')
    print("")
    print("Open in Obsidian:")
    print(f"  {paths['root_dir'].as_posix()}")
    print("")
    if workspace_root:
        print("Next command:")
        print(
            "  codex-memory ingest --text "
            '"Initialize memory compiler for this project." '
            '--title "Memory Setup" --source-type codex-summary '
            f'--workspace "{workspace_root.as_posix()}"'
        )
    else:
        print("Next command:")
        print(
            '  codex-memory ingest --text "Initialize memory compiler for this project." '
            '--title "Memory Setup" --source-type codex-summary'
        )
    if readme_path:
        print("")
        print(f"Wrote guide: {readme_path.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
