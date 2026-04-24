---
name: memory-ingest
description: Capture session context into daily logs through deterministic ingest.
---

# memory-ingest

Use this skill when the user asks to save session memory or transcript context.

## Steps
1. Prefer a structured summary whenever you have durable decisions, blockers, validation, or future plans to save.
2. For quick notes, run `uv run python scripts/ingest.py --text "..." --source-type codex-summary`.
3. For structured recaps, either pass multiline `--text` content with `##` headings, use the direct section flags for an implementation batch, or save the recap to a markdown file and use `--file`.
4. Supported headings are:
   - `## Goal`
   - `## Summary`
   - `## Current Status`
   - `## Decisions`
   - `## Decision Links`
   - `## Blockers`
   - `## Files`
   - `## Validation`
   - `## Verification State`
   - `## Evidence`
   - `## Next Steps`
   - `## Open Questions`
   - `## Date Context`
5. For low-friction implementation-batch ingest, prefer direct flags such as:
   - `uv run python scripts/ingest.py --goal "..." --current-status "..." --decision "..." --file-touched path --validation "..." --next-step "..." --open-question "..."`
   - add `--decision-link "supersedes: [[decisions/...]]"` or `--decision-link "blocked_by: ..."` when relationship tracking matters
6. For transcript-style context, save text to a temp markdown file and run:
   - `uv run python scripts/ingest.py --file <path> --session-id <id> --title "<title>" --source-type <note|codex-summary|commit-summary|pr-summary>`
   - `uv run python scripts/ingest.py --codex-chat-file <path> --session-id <id> --title "<title>"`
7. Put future plans under `## Next Steps` instead of inventing a separate plan format.
8. Attach `--workspace`, `--repo`, and `--task-ref` when the context comes from a specific codebase task.
9. Verify the latest `daily/YYYY-MM-DD.md` has a new titled `### ... (HH:MM)` block with `Session ID` and `Source Type`.
10. Expect ingest to compile and lint automatically. Use `--no-compile --no-lint` only when intentionally deferring maintenance.

## Guardrails
- Never rewrite prior session sections in daily logs.
- Append-only behavior only.
