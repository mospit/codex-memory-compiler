"""Shared CLI targeting and root bootstrap helpers."""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class TargetSelection:
    """Resolved target information for a command invocation."""

    root_dir: Path
    workspace_root: Path | None
    remaining_args: list[str]


def configure_stdio() -> None:
    """Avoid Windows console encoding crashes on stored markdown content."""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None or not hasattr(stream, "reconfigure"):
            continue
        stream.reconfigure(encoding="utf-8", errors="replace")


def parse_targeting_args(argv: list[str]) -> tuple[argparse.Namespace, list[str]]:
    """Parse root-targeting flags while leaving command-specific args intact."""
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("--root")
    parser.add_argument("--workspace-root")
    return parser.parse_known_args(argv)


def resolve_target_selection(
    argv: list[str],
    *,
    legacy_default_root: bool,
    cwd: Path | None = None,
) -> TargetSelection:
    """Resolve the active memory root for a command invocation."""
    args, remaining = parse_targeting_args(argv)
    current_dir = (cwd or Path.cwd()).resolve()

    if args.root:
        root_dir = Path(args.root).expanduser().resolve()
        workspace_root = None
    elif args.workspace_root:
        workspace_root = Path(args.workspace_root).expanduser().resolve()
        if not workspace_root.exists():
            raise SystemExit(f"Workspace root not found: {workspace_root}")
        if not workspace_root.is_dir():
            raise SystemExit(f"Workspace root is not a directory: {workspace_root}")
        root_dir = (workspace_root / ".codex-memory").resolve()
    else:
        env_root = os.getenv("KB_ROOT_DIR")
        if env_root:
            root_dir = Path(env_root).expanduser().resolve()
            workspace_root = None
        elif legacy_default_root:
            root_dir = current_dir
            workspace_root = None
        elif current_dir.name == ".codex-memory":
            root_dir = current_dir
            workspace_root = current_dir.parent
        else:
            root_dir = (current_dir / ".codex-memory").resolve()
            workspace_root = current_dir

    if root_dir.exists() and not root_dir.is_dir():
        raise SystemExit(f"Memory root is not a directory: {root_dir}")

    return TargetSelection(root_dir=root_dir, workspace_root=workspace_root, remaining_args=remaining)


def activate_root(root_dir: Path) -> None:
    """Publish the active root to the package runtime."""
    os.environ["KB_ROOT_DIR"] = str(root_dir)


def ensure_memory_root(root_dir: Path) -> None:
    """Create the memory scaffold for a resolved root."""
    activate_root(root_dir)
    from .utils import ensure_memory_root_scaffold

    ensure_memory_root_scaffold(root_dir)


def query_is_write_mode(argv: list[str]) -> bool:
    """Return whether query args request a write operation."""
    return "--file-back" in argv
