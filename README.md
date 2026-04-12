# Codex Memory Compiler

A markdown-first personal memory system designed for Codex app workflows.

The package keeps the original memory-compiler architecture intact:
- `daily/` as append-only source logs
- `knowledge/` as compiled concept, connection, and Q&A articles
- `knowledge/index.md` as the retrieval catalog
- `knowledge/log.md` as the append-only compile/query history

## What Changed

- The project is Codex-first rather than Claude-dependent.
- The supported CLI is `codex-memory`, available through `uv run codex-memory`.
- Repo-local Codex skills live under `.agents/skills/`.
- Exported Codex markdown chats can be ingested directly.
- Compile, query, and lint remain deterministic and markdown-native.

## Quick Start

```bash
uv sync
uv run codex-memory --help
uv run codex-memory compile --root .
uv run codex-memory query --root . "What does this memory compiler know already?" --explain
```

Use `--root .` when running inside this repository so the active memory root is explicit even if your shell has `KB_ROOT_DIR` set elsewhere.

## Codex App Flow

1. Open this repository in Codex app.
2. Ask Codex to read `AGENTS.md`.
3. Use the repo skills:
   - `.agents/skills/memory-ingest`
   - `.agents/skills/memory-compile`
   - `.agents/skills/memory-query`
   - `.agents/skills/memory-lint`

Typical loop:
1. Ingest recent work into `daily/`
2. Compile the corpus into `knowledge/`
3. Query the knowledge base through the index
4. Lint for structural issues and safe maintenance fixes

## CLI Commands

```bash
uv run codex-memory init --workspace-root D:/projects/other-project
uv run codex-memory ingest --root . --text "Worked on memory compiler docs." --source-type codex-summary
uv run codex-memory ingest --root . --file notes/session.md --session-id codex-manual-001 --title "Portal Auth Review" --source-type pr-summary
uv run codex-memory ingest --root . --codex-chat-file exports/codex-chat.md --session-id codex-chat-001 --title "Codex Chat Capture" --compile --lint
uv run codex-memory compile --root .
uv run codex-memory query --root . "What did I decide about the workflow?" --explain
uv run codex-memory query --root . "What changed this week?" --file-back
uv run codex-memory lint --root . --structural-only
uv run codex-memory lint --root . --autofix
```

## Mini Guides

### Capture a short session in this repo

```bash
uv run codex-memory ingest --root . --text "Validated the packaged codex-memory CLI in this repository and updated the README." --title "CLI Validation" --source-type codex-summary
uv run codex-memory compile --root .
```

### Ingest an exported Codex chat

```bash
uv run codex-memory ingest --root . --codex-chat-file exports/codex-chat.md --session-id codex-chat-001 --title "Codex Chat Capture" --compile --lint
```

### Ask the compiled knowledge base a question

```bash
uv run codex-memory query --root . "What did we decide about using git commits as an ingest source?" --explain
```

### Use this checkout with another project

```bash
uv run codex-memory init --workspace-root D:/projects/other-project
uv run codex-memory ingest --workspace-root D:/projects/other-project --text "Worked on auth migration." --title "Auth Migration" --source-type codex-summary --workspace "D:/projects/other-project" --repo "owner/other-project"
uv run codex-memory compile --workspace-root D:/projects/other-project
uv run codex-memory query --workspace-root D:/projects/other-project "What did I do in the other project?" --explain
```

## Root Targeting

The CLI resolves the memory root in this order:

1. `--root PATH`
2. `--workspace-root PATH` which maps to `<workspace>/.codex-memory`
3. `KB_ROOT_DIR`
4. the current working directory's `.codex-memory`

Practical guidance:
- Use `--root .` when you want this repository itself to be the memory root.
- Use `--workspace-root PATH` when you want a separate project's memory under its own `.codex-memory/`.
- Prefer explicit flags over ambient `KB_ROOT_DIR` when you are switching between projects.

## Data Model

- Daily sessions carry `session_id`, `title`, `source_type`, and optional `workspace` / `repo` / `task_ref`.
- Supported ingest source types include `note`, `codex-summary`, `commit-summary`, `pr-summary`, and `codex-chat`.
- Compiled concept articles carry `concept_id`, `aliases`, `keywords`, `summary`, `source_sessions`, and `source_logs`.
- Connection articles are generated deterministically when concept co-occurrence reaches the configured threshold.

## Tests

```bash
py -3 -m unittest discover -s tests -v
```

## Optional Integrations

- `integrations/claude-hooks/` contains compatibility-only Claude lifecycle hook scripts.
- These are not required for Codex app usage.
- The supported fallback path is the `codex-memory` CLI.

## Docs

- `AGENTS.md` - operating spec for this repository
- `CODEX_DESKTOP_USAGE.md` - Codex desktop workflow notes
- `OPERATING_GUIDE.md` - practical usage paths and limitations
- `MIGRATION_PLAN.md` - migration rationale and phased plan
