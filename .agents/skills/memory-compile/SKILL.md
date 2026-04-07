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
4. Run lint after compile: `uv run python scripts/lint.py --structural-only`.

## Quality checks
- Articles must retain YAML frontmatter.
- Index rows must point to actual article paths.
- Build log entries must be append-only.
