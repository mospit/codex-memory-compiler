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

## Sample walkthrough (isolated fixtures)

Use the bundled demo corpus in `sample/demo-context/`:

```bash
uv run python scripts/run_sample.py
```

Expected outputs from the isolated run:
- `daily/YYYY-MM-DD.md` with appended `### Session (HH:MM)` entries.
- `knowledge/concepts/*.md` concept articles with YAML frontmatter.
- `knowledge/index.md` and `knowledge/log.md` updated coherently.
- Query output with `## Sources Consulted`.
- `reports/lint-YYYY-MM-DD.md`.

## Optional Codex hook scaffold

If your Codex environment supports local lifecycle command hooks, you can optionally use:
- `integrations/codex-hooks/session-start.py`
- `integrations/codex-hooks/session-stop.py`

These wrappers are optional convenience helpers around the same deterministic scripts and are never required for normal operation.

## Deterministic vs optional model-assisted behavior

- Deterministic: ingest parsing, compile transforms, index-guided query selection, structural lint.
- Optional future model assistance: semantic contradiction analysis and richer synthesis through `scripts/model_adapter.py`.

## Limitations / platform notes

- Automatic lifecycle hooks are not guaranteed in all Codex app/cloud environments.
- Semantic contradiction detection is currently manual/review-driven in Codex mode.
- Deterministic compile/query behavior is intentionally conservative for reliability.
- The optional Claude integration in `integrations/claude-hooks/` is compatibility-only and not required.

## Troubleshooting quick checks

- Run `uv run python scripts/compile.py --dry-run` to confirm what will compile.
- If query quality seems weak, verify index rows exist for expected concept pages.
- Run `uv run python -m unittest tests/test_pipeline.py` to validate the baseline pipeline.
