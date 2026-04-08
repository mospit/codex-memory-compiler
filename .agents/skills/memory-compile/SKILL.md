---
name: memory-compile
description: Compile daily logs into knowledge articles and update index/log.
---

# memory-compile

Use this skill when asked to compile memories into the markdown KB.

## Steps
1. Run `uv run python scripts/compile.py`.
2. If targeting specific logs, run `uv run python scripts/compile.py --file daily/<date>.md`.
3. Inspect changed files under `knowledge/`:
   - `knowledge/concepts/*.md`
   - `knowledge/index.md`
   - `knowledge/log.md`
   - `knowledge/connections/*.md`
4. Remember that compile rebuilds the KB using the full daily-log corpus so concept merging stays deterministic.
5. Run lint after compile: `uv run python scripts/lint.py --autofix`.

## Quality checks
- Articles must retain YAML frontmatter with `concept_id` / `connection_id`, `summary`, `source_sessions`, and `source_logs`.
- Index rows must point to actual article paths and reflect current summaries.
- Build log entries must be append-only.
