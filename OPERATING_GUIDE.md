# Operating Guide

## Best experience path (Codex app)

1. Open repository in Codex app.
2. Ask Codex to read `AGENTS.md` and use `.agents/skills` workflows.
3. Run the memory loop:
   - ingest session context
   - compile the corpus into canonical concepts and connections
   - query knowledge through the index
   - lint and apply safe autofixes when useful
4. Commit incremental changes to keep memory history reviewable.

## Works-everywhere fallback path (no hooks)

Use these commands directly:

```bash
uv run python scripts/ingest.py --text "Session summary" --source-type codex-summary
uv run python scripts/compile.py
uv run python scripts/query.py "What did I decide about X?" --explain
uv run python scripts/lint.py --autofix
```

For richer ingest, pass a markdown context file:

```bash
uv run python scripts/ingest.py --file path/to/context.md --session-id my-session-123 --title "Portal Auth Review" --source-type pr-summary
```

Useful optional metadata:

- `--workspace`
- `--repo`
- `--task-ref`

## Limitations / platform notes

- Automatic lifecycle hooks are not guaranteed in all Codex app/cloud environments.
- Compile is corpus-wide because concept merging and connection generation are deterministic across the full daily-log set.
- Conflict detection is heuristic and advisory; deterministic compile/query behavior remains intentionally conservative for reliability.
- The optional Claude integration in `integrations/claude-hooks/` is compatibility-only and not required.
