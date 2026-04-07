# Codex Hook Scaffold (Optional)

This folder provides an **optional** scaffold for users who want session lifecycle automation in environments where Codex can run local commands.

These hooks are convenience wrappers only:
- The repository remains fully functional without them.
- Core workflow is still `ingest -> compile -> query -> lint` via `scripts/*.py`.

## Files
- `session-start.py`: creates a local session context template under `scripts/.tmp/`.
- `session-stop.py`: converts a context markdown file into an appended daily log via `scripts/flush.py`.

## Example usage

```bash
# Start a draft context
uv run python integrations/codex-hooks/session-start.py --session-id codex-demo

# Edit the emitted markdown with User/Assistant lines, then stop session
uv run python integrations/codex-hooks/session-stop.py \
  --context-file scripts/.tmp/session-codex-demo.md \
  --session-id codex-demo
```

## Notes
- `session-stop.py` accepts `--no-compile-trigger` to disable the after-hours auto-compile behavior.
- If your Codex environment has no hook runner, run these scripts manually or skip them entirely.
