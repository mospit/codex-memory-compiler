---
name: memory-session-summary
description: "Summarize the current Codex session into an ingest-ready recap and append it to daily logs with scripts/ingest.py. Use when Codex needs to save the current session, capture a concise work summary, or store a Codex recap without exporting the full chat."
---

# Memory Session Summary

Use this skill when the user wants the current session summarized and ingested as `codex-summary` memory.

## Steps
1. Gather only durable facts from the current thread and workspace:
   - task or goal
   - key decisions or behavior changes
   - files touched
   - validation commands and outcomes
   - blockers, follow-ups, or next steps
2. Omit transient chat, abandoned ideas, and claims that were not confirmed by the work.
3. Draft a concise recap in markdown. Prefer a title that will still be useful during retrieval, such as `Prism session summary - portal auth callback fixes`.
4. Run commands from the repository root.
5. Choose the ingest path:
   - For a short recap, run `uv run python scripts/ingest.py --text "<summary>" --title "<title>" --source-type codex-summary`
   - For structured bullets or multi-section notes, save the recap to a temp markdown file and run `uv run python scripts/ingest.py --file <path> --session-id <session-id> --title "<title>" --source-type codex-summary`
6. Add `--workspace`, `--repo`, and `--task-ref` when those values are known and improve retrieval later.
7. Expect `scripts/ingest.py` to compile and lint automatically after the daily-log append.
8. Use `--no-compile --no-lint` only when intentionally deferring maintenance, such as bulk ingest or fixture setup.
9. Verify that `daily/YYYY-MM-DD.md` has a new append-only section with the chosen title, `Session ID`, and `Source Type`.

## Summary Shape

Prefer this full structure when the information exists:

```markdown
## Goal
- Start ...

## Summary
- Fixed ...
- Decided ...

## Current Status
- Implemented locally ...

## Decisions
- Keep ...

## Decision Links
- supersedes: [[decisions/...]]
- implemented_by: apps/portal/lib/beta-access.ts
- blocked_by: production env setup

## Blockers
- Waiting on ...

## Files
- src/ui/...
- docs/...

## Validation
- npm run check
- not run: ...

## Verification State
- Tests pass locally; production verification pending.

## Evidence
- Verified ...

## Next Steps
- ...

## Open Questions
- ...

## Date Context
- State captured as of 2026-04-12.
```

Put future plans under `## Next Steps`. Omit any section that truly does not apply, but prefer explicit sections over a loose paragraph when the session includes decisions, blockers, validation, or evidence.

## Guardrails
- Prefer confirmed outcomes over exhaustive narration.
- Keep the recap short enough to remain useful during later compile and query steps.
- Say that the session is partial when the work is incomplete instead of inventing conclusions.
- Never rewrite older daily-log sections while ingesting a new recap.
