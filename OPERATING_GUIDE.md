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
uv run python scripts/ingest.py --codex-chat-file exports/codex-chat.md --session-id codex-chat-001 --compile --lint
uv run python scripts/compile.py
uv run python scripts/query.py "What did I decide about X?" --explain
uv run python scripts/lint.py --autofix
```

For richer ingest, pass a markdown context file:

```bash
uv run python scripts/ingest.py --file path/to/context.md --session-id my-session-123 --title "Portal Auth Review" --source-type pr-summary
```

For exported Codex chat capture, prefer a markdown conversation export:

```bash
uv run python scripts/ingest.py --codex-chat-file exports/codex-chat.md --session-id codex-chat-001 --title "Codex Chat Capture" --compile --lint
```

Useful optional metadata:

- `--workspace`
- `--repo`
- `--task-ref`

## Limitations / platform notes

- Automatic lifecycle hooks are not guaranteed in all Codex app/cloud environments.
- Compile is corpus-wide because concept merging and connection generation are deterministic across the full daily-log set.
- Conflict detection is heuristic and advisory; deterministic compile/query behavior remains intentionally conservative for reliability.
- Codex chat capture is export-driven today; there is no supported Codex-native session-end hook in this repository yet.
- The optional Claude integration in `integrations/claude-hooks/` is compatibility-only and not required.
