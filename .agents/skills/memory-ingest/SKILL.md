---
name: memory-ingest
description: Capture session context into daily logs through deterministic ingest.
---

# memory-ingest

Use this skill when the user asks to save session memory or transcript context.

## Steps
1. Prefer `uv run python scripts/ingest.py --text "..." --source-type codex-summary` for quick notes.
2. For transcript-style context, save text to a temp markdown file and run:
   - `uv run python scripts/ingest.py --file <path> --session-id <id> --title "<title>" --source-type <note|codex-summary|commit-summary|pr-summary>`
   - `uv run python scripts/ingest.py --codex-chat-file <path> --session-id <id> --title "<title>" --compile --lint`
3. Attach `--workspace`, `--repo`, and `--task-ref` when the context comes from a specific codebase task.
4. Verify the latest `daily/YYYY-MM-DD.md` has a new titled `### ... (HH:MM)` block with `Session ID` and `Source Type`.
5. If requested, run `uv run python scripts/compile.py` after ingest.

## Guardrails
- Never rewrite prior session sections in daily logs.
- Append-only behavior only.
