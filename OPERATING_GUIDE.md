# Operating Guide

## Best experience path (Codex app)

1. Open repository in Codex app.
2. Ask Codex to read `AGENTS.md` and use `.agents/skills` workflows.
3. Run the memory loop:
   - ingest session context
   - compile knowledge
   - query knowledge
   - lint and fix structural issues
4. Commit incremental changes to keep memory history reviewable.

## Works-everywhere fallback path (no hooks)

Use these commands directly:

```bash
uv run python scripts/ingest.py --text "Session summary"
uv run python scripts/compile.py
uv run python scripts/query.py "What did I decide about X?"
uv run python scripts/lint.py --structural-only
```

For richer ingest, pass a markdown context file:

```bash
uv run python scripts/ingest.py --file path/to/context.md --session-id my-session-123
```

## Limitations / platform notes

- Automatic lifecycle hooks are not guaranteed in all Codex app/cloud environments.
- Semantic contradiction detection is currently manual/review-driven in Codex mode.
- Deterministic compile/query behavior is intentionally conservative for reliability.
- The optional Claude integration in `integrations/claude-hooks/` is compatibility-only and not required.
