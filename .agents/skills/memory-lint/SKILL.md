---
name: memory-lint
description: Run structural health checks on the markdown knowledge base.
---

# memory-lint

Use this skill to assess KB quality and consistency.

## Steps
1. Run `uv run python scripts/lint.py --structural-only` for fast checks.
2. Run `uv run python scripts/lint.py` when user wants full reminder output.
3. Open the generated report under `reports/lint-YYYY-MM-DD.md`.
4. Fix errors first (broken links), then warnings, then suggestions.

## Scope
- Structural checks are deterministic.
- Semantic contradiction analysis is currently manual/review-driven in Codex mode.
