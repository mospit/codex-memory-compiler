---
name: memory-ingest
description: Capture session context into daily logs through deterministic ingest.
---

# memory-ingest

Use this skill when the user asks to save session memory or transcript context.

## Steps
1. Prefer `uv run python scripts/ingest.py --text "..."` for quick notes.
2. For transcript-style context, save text to a temp markdown file and run:
   - `uv run python scripts/ingest.py --file <path> --session-id <id>`
3. Verify the latest `daily/YYYY-MM-DD.md` has a new `### Session (HH:MM)` block.
4. If requested, run `uv run python scripts/compile.py` after ingest.

## Guardrails
- Never rewrite prior session sections in daily logs.
- Append-only behavior only.
