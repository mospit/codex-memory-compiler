# Codex Memory Compiler

A markdown-first personal memory system designed for **Codex app workflows**.

This project preserves the original memory-compiler architecture:
- `daily/` conversation logs as immutable source
- `knowledge/` compiled concept/connection/Q&A articles
- `knowledge/index.md` as the retrieval catalog for index-guided retrieval
- `knowledge/log.md` as append-only build/query log

## What changed from the original Claude-oriented version

- Removed hard runtime dependency on Claude Agent SDK.
- Added deterministic fallback workflows so the project is useful without hooks.
- Introduced a thin model adapter boundary (`scripts/model_adapter.py`) for optional future integrations.
- Repositioned hooks as optional compatibility scaffolding under `integrations/claude-hooks/`.
- Added Codex repository skills in `.agents/skills/` for ingest/compile/query/lint tasks.
- Added stable session metadata, canonical concept merging, deterministic connection generation, and fixture-based tests.

## Quick start (Codex app first)

1. Open this repository in Codex app.
2. Ask Codex to follow `AGENTS.md`.
3. Use repository skills:
   - `.agents/skills/memory-ingest`
   - `.agents/skills/memory-compile`
   - `.agents/skills/memory-query`
   - `.agents/skills/memory-lint`

Typical loop:
1. Ingest recent work into `daily/`
2. Compile the daily-log corpus into `knowledge/`
3. Query the compiled KB through the index
4. Lint for health and apply safe autofixes when needed

## CLI/manual fallback (works without hooks)

```bash
uv sync
uv run python scripts/ingest.py --text "Worked on migration plan and codex workflow" --source-type codex-summary
uv run python scripts/compile.py
uv run python scripts/query.py "What changed in the migration?" --explain
uv run python scripts/lint.py --autofix
```

## Commands

```bash
uv run python scripts/ingest.py --text "..."           # manual session ingest
uv run python scripts/ingest.py --text "..." --title "Auth Migration" --source-type codex-summary
uv run python scripts/ingest.py --file notes/session.md --session-id codex-manual-001
uv run python scripts/compile.py                        # rebuild KB from the daily-log corpus when changes exist
uv run python scripts/compile.py --all                  # force recompile all logs
uv run python scripts/query.py "question"               # ask KB through index-guided shortlisting
uv run python scripts/query.py "question" --explain     # show shortlist and ranking reasons
uv run python scripts/query.py "question" --file-back   # ask + save Q&A article
uv run python scripts/lint.py                           # structural + conflict heuristic checks
uv run python scripts/lint.py --autofix                 # repair stale index rows and missing backlinks
uv run python scripts/lint.py --structural-only         # structural checks only
```

## Data model

- Daily sessions now carry stable `session_id`, `title`, `source_type`, and optional `workspace` / `repo` / `task_ref` metadata.
- Compiled concept articles carry `concept_id`, `aliases`, `keywords`, `summary`, `source_sessions`, and `source_logs`.
- Connection articles are generated deterministically when concept co-occurrence reaches the configured threshold.

## Tests

```bash
py -3 -m unittest discover -s tests -v
```

## Optional integrations

- `integrations/claude-hooks/` contains legacy Claude lifecycle hook scripts.
- These are not required for Codex app usage.
- If unavailable in your environment, use manual ingest commands.

## Docs

- `AGENTS.md` - Codex operating spec for this repository
- `MIGRATION_PLAN.md` - migration rationale and phased plan
- `OPERATING_GUIDE.md` - practical day-to-day usage paths and limitations
