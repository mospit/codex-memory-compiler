# Operating Guide

## Best experience path (Codex app)

1. Open repository in Codex app.
2. Ask Codex to read `AGENTS.md` and use `.agents/skills` workflows.
3. Run the memory loop:
   - ingest session context
   - compile the corpus into canonical concepts and connections
   - in Obsidian, review `knowledge/dashboards/open-followups.md` for open work and recent decisions
   - lint and apply safe autofixes when useful
4. Commit incremental changes to keep memory history reviewable.

## Obsidian view

Use `knowledge/dashboards/open-followups.md` as the main Obsidian review page.

- `## Open Follow-Ups` is the current pending-work view and comes only from explicit action items
- `## Recent Decisions` is the completed-decisions view and comes from `knowledge/decisions/`
- if you want “decisions I still need to make,” record them as explicit `## Next Steps` during ingest; the dashboard does not infer undecided questions

## Works-everywhere fallback path (no hooks)

Use these commands directly:

```bash
uv run python scripts/ingest.py --text "Session summary" --source-type codex-summary
uv run python scripts/ingest.py --codex-chat-file exports/codex-chat.md --session-id codex-chat-001
uv run python scripts/compile.py
uv run python scripts/query.py "What did I decide about X?" --explain --evidence
uv run python scripts/lint.py --autofix
```

For richer ingest, pass a markdown context file:

```bash
uv run python scripts/ingest.py --file path/to/context.md --session-id my-session-123 --title "Portal Auth Review" --source-type pr-summary
```

For high-signal session capture, prefer a structured summary:

```markdown
## Summary
- Fixed the compile ranking drift.

## Decisions
- Emit decision articles only from explicit Decisions items.

## Blockers
- Golden fixtures still need refresh.

## Files
- scripts/query.py
- tests/test_memory_compiler_e2e.py

## Validation
- py -3 -m unittest tests.test_query tests.test_compile -v

## Evidence
- Verified excerpts now include `daily/...:line` references.

## Next Steps
- Refresh the e2e goldens after the new decision pages land.

## Date Context
- State captured as of 2026-04-12.
```

You can pass that either as multiline `--text` input or through `--file`. Keep future plans under `## Next Steps`; there is no separate plan article type in this phase.

`scripts/ingest.py` compiles and lints automatically after appending the daily-log entry. Use `--no-compile --no-lint` only when intentionally deferring maintenance.

For exported Codex chat capture, prefer a markdown conversation export:

```bash
uv run python scripts/ingest.py --codex-chat-file exports/codex-chat.md --session-id codex-chat-001 --title "Codex Chat Capture"
```

Useful optional metadata:

- `--workspace`
- `--repo`
- `--task-ref`
- `--evidence` on `query.py` to append source-backed excerpts with daily-log line references

## Limitations / platform notes

- Automatic lifecycle hooks are not guaranteed in all Codex app/cloud environments.
- Compile is corpus-wide because concept merging and connection generation are deterministic across the full daily-log set.
- Conflict detection is heuristic and advisory; deterministic compile/query behavior remains intentionally conservative for reliability.
- Codex chat capture is export-driven today; there is no supported Codex-native session-end hook in this repository yet.
- The optional Claude integration in `integrations/claude-hooks/` is compatibility-only and not required.
