# Codex Memory Compiler

A markdown-first personal memory system designed for **Codex app workflows**.

This project preserves the original memory-compiler architecture:
- `daily/` conversation logs as immutable source
- `knowledge/` compiled concept/connection/Q&A articles
- `knowledge/index.md` as the retrieval catalog (index-guided, no vector DB required)
- `knowledge/log.md` as append-only build/query log

## What changed from the original Claude-oriented version

- Removed hard runtime dependency on Claude Agent SDK.
- Added deterministic fallback workflows so the project is useful without hooks.
- Introduced a thin model adapter boundary (`scripts/model_adapter.py`) for optional future integrations.
- Repositioned hooks as optional compatibility scaffolding under `integrations/claude-hooks/`.
- Added Codex repository skills in `.agents/skills/` for ingest/compile/query/lint tasks.

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
2. Compile daily logs into `knowledge/`
3. Query the compiled KB
4. Lint for health and fix issues

## CLI/manual fallback (works without hooks)

```bash
uv sync
uv run python scripts/ingest.py --text "Worked on migration plan and codex workflow"
uv run python scripts/compile.py
uv run python scripts/query.py "What changed in the migration?"
uv run python scripts/lint.py --structural-only
```

## End-to-end sample (isolated demo corpus)

Run a full deterministic demo without touching your real `daily/` and `knowledge/` folders:

```bash
uv run python scripts/run_sample.py
```

The demo loads fixture sessions from `sample/demo-context/`, then runs ingest, compile, query, and lint in an isolated temporary workspace.

## Commands

```bash
uv run python scripts/ingest.py --text "..."           # manual session ingest
uv run python scripts/ingest.py --file notes/session.md # ingest from prepared context
uv run python scripts/compile.py                        # compile new/changed logs
uv run python scripts/compile.py --all                  # force recompile all logs
uv run python scripts/query.py "question"               # ask KB
uv run python scripts/query.py "question" --file-back   # ask + save Q&A article
uv run python scripts/lint.py                           # structural + semantic reminder
uv run python scripts/lint.py --structural-only         # structural checks only
uv run python scripts/run_sample.py                     # isolated fixture demo pipeline
uv run python -m unittest tests/test_pipeline.py        # core deterministic sanity test
```

## Optional integrations

- `integrations/claude-hooks/` contains legacy Claude lifecycle hook scripts.
- `integrations/codex-hooks/` contains optional Codex-oriented session start/stop wrappers.
- These are not required for Codex app usage.
- If unavailable in your environment, use manual ingest commands.

## Deterministic today vs model-assisted later

- Deterministic today:
  - ingest structure extraction
  - compile article generation + index/log updates
  - keyword/index-guided retrieval
  - structural lint checks
- Model-assisted later (optional, via `scripts/model_adapter.py` boundary):
  - semantic contradiction detection
  - richer synthesis and normalization

## Troubleshooting

- **No query results:** run `uv run python scripts/compile.py` and retry.
- **Unexpected stale warnings:** re-run compile to refresh source hashes in `scripts/state.json`.
- **Hook scripts not available in your Codex environment:** skip hooks and use direct script commands.

## Docs

- `AGENTS.md` - Codex operating spec for this repository
- `MIGRATION_PLAN.md` - migration rationale and phased plan
- `OPERATING_GUIDE.md` - practical day-to-day usage paths and limitations
