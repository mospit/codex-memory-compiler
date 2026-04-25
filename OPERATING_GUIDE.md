# Operating Guide

## Positioning

Codex Memory Compiler is a repo-scoped, markdown-first compiler for project
memory. Use it for decisions, goals, follow-ups, evidence, and status that
should be inspectable in the repo or in a project-local `.codex-memory/` folder.

It complements Codex native memories instead of replacing them. Native memories
can help with local recall across conversations; this project produces explicit
markdown artifacts that can be reviewed, versioned, linted, and queried before
planning.

## Codex App Path

1. Open the repository in Codex app.
2. Ask Codex to read `AGENTS.md` and use `.agents/skills` workflows.
3. Run the memory loop:
   - ingest session context
   - compile the corpus into canonical concepts and connections
   - query before planning
   - in Obsidian, review `knowledge/dashboards/open-followups.md` for open work and recent decisions
   - lint and apply safe autofixes when useful
4. Commit incremental changes when generated memory artifacts are intended to be shared.

## Solo Dogfood Path

Use this path when running the compiler directly from a terminal:

```bash
uv sync
uv run codex-memory init --workspace-root D:/projects/other-project
uv run codex-memory ingest --workspace-root D:/projects/other-project --text "Session summary" --source-type codex-summary
uv run codex-memory compile --workspace-root D:/projects/other-project
uv run codex-memory query --workspace-root D:/projects/other-project "What did I decide about X?" --plan-brief --explain
uv run codex-memory lint --workspace-root D:/projects/other-project --structural-only
```

Use `--root .` when the current repository is the memory root. Prefer explicit
root flags over ambient `KB_ROOT_DIR` when switching between projects.

## Automation Path

Automation is planned as explicit source adapters, not hidden background capture.
The high-value adapters are:

- `ingest-git --since HEAD~10` for commit messages and touched files
- `ingest-pr --file pr.md` or GitHub CLI integration for PR summaries
- `ingest-issue --file issue.md` for issue context
- `ingest-codex-memory --path ~/.codex/memories --read-only` for importing context without editing Codex-owned state
- `ingest-transcript --format codex|claude|raw` for exported conversations

Until these exist, use structured session summaries or exported markdown chats.

## Obsidian View

Use `knowledge/dashboards/open-followups.md` as the main Obsidian review page.

- `## Open Follow-Ups` is the current pending-work view and comes only from explicit action items.
- `## Recent Decisions` is the completed-decisions view and comes from `knowledge/decisions/`.
- If you want "decisions I still need to make," record them as explicit `## Next Steps` during ingest; the dashboard does not infer undecided questions.

## Works-Everywhere Fallback Path

Use these commands directly:

```bash
uv run codex-memory ingest --root . --text "Session summary" --source-type codex-summary
uv run codex-memory ingest --root . --codex-chat-file exports/codex-chat.md --session-id codex-chat-001
uv run codex-memory compile --root .
uv run codex-memory query --root . "What did I decide about X?" --explain --evidence
uv run codex-memory lint --root . --autofix
```

For richer ingest, pass a markdown context file:

```bash
uv run codex-memory ingest --root . --file path/to/context.md --session-id my-session-123 --title "Portal Auth Review" --source-type pr-summary
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

You can pass that either as multiline `--text` input or through `--file`. Keep
future plans under `## Next Steps`; there is no separate plan article type in
this phase.

`codex-memory ingest` compiles and lints automatically after appending the
daily-log entry. Use `--no-compile --no-lint` only when intentionally deferring
maintenance.

For exported Codex chat capture, prefer a markdown conversation export:

```bash
uv run codex-memory ingest --root . --codex-chat-file exports/codex-chat.md --session-id codex-chat-001 --title "Codex Chat Capture"
```

Useful optional metadata:

- `--workspace`
- `--repo`
- `--task-ref`
- `--evidence` on `query` to append source-backed excerpts with daily-log line references

## Limitations / Platform Notes

- Automatic lifecycle hooks are not guaranteed in all Codex app/cloud environments.
- Codex chat capture is export-driven today; there is no supported Codex-native session-end hook in this repository yet.
- Compile is corpus-wide because concept merging and connection generation are deterministic across the full daily-log set.
- Conflict detection is heuristic and advisory; deterministic compile/query behavior remains intentionally conservative for reliability.
- The optional Claude integration in `integrations/claude-hooks/` is compatibility-only and not required.
- See `docs/roadmap.md` for planned source adapters, review/diff workflow, lifecycle controls, and retrieval improvements.
- See `docs/threat-model.md` before committing or sharing generated memory artifacts.
