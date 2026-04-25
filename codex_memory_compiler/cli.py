"""Installed console entrypoint for Codex Memory Compiler."""

from __future__ import annotations

import importlib
import sys

from .targeting import (
    activate_root,
    configure_stdio,
    ensure_memory_root,
    query_is_write_mode,
    resolve_target_selection,
)

COMMANDS = {"init", "ingest", "ingest-git", "compile", "query", "lint"}


def render_help() -> str:
    lines = [
        "usage: codex-memory <command> [options]",
        "",
        "commands:",
        "  init      create or verify a .codex-memory root",
        "  ingest    save session context into daily logs",
        "  ingest-git  import recent git commits into daily logs",
        "  compile   rebuild knowledge from daily logs",
        "  query     ask the compiled knowledge base",
        "  lint      run knowledge base health checks",
        "",
        "shared options:",
        "  --root PATH            explicit memory root",
        "  --workspace-root PATH  workspace that owns <workspace>/.codex-memory",
    ]
    return "\n".join(lines)


def is_write_command(command: str, argv: list[str]) -> bool:
    if command in {"init", "ingest", "ingest-git", "compile", "lint"}:
        return True
    if command == "query":
        return query_is_write_mode(argv)
    return False


def dispatch(command: str, argv: list[str], *, legacy_default_root: bool) -> int:
    selection = resolve_target_selection(argv, legacy_default_root=legacy_default_root)
    root_dir = selection.root_dir
    remaining_args = selection.remaining_args
    wants_help = any(arg in {"-h", "--help"} for arg in remaining_args)

    if command == "init":
        from . import init as init_module

        if wants_help:
            return int(init_module.main(remaining_args) or 0)
        activate_root(root_dir)
        return int(init_module.main(root_dir=root_dir, workspace_root=selection.workspace_root) or 0)

    if wants_help:
        activate_root(root_dir)
    elif is_write_command(command, remaining_args):
        ensure_memory_root(root_dir)
    else:
        activate_root(root_dir)
        if not root_dir.exists():
            raise SystemExit(
                f"Memory root not found: {root_dir}\n"
                "Run `codex-memory init` or use a write command like `codex-memory ingest ...` first."
            )

    module = importlib.import_module(f".{command.replace('-', '_')}", package=__package__)
    return int(module.main(remaining_args) or 0)


def main(argv: list[str] | None = None, *, legacy_default_root: bool = False) -> int:
    configure_stdio()
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in {"-h", "--help"}:
        print(render_help())
        return 0

    command, remaining = args[0], args[1:]
    if command not in COMMANDS:
        print(render_help(), file=sys.stderr)
        raise SystemExit(f"Unknown command: {command}")

    return dispatch(command, remaining, legacy_default_root=legacy_default_root)
