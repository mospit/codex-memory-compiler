# Codex Memory Compiler

A markdown-first personal memory system designed for **Codex app workflows**.

This project preserves the original memory-compiler architecture:
- `daily/` conversation logs as immutable source
- `knowledge/` compiled concept/connection/Q&A articles
- `knowledge/index.md` as the retrieval catalog for index-guided retrieval
- `knowledge/log.md` as append-only build/query log

## What changed from the original Claude-oriented version

- Removed hard runtime dependency on Claude Agent SDK.
- Added deterministic fallback workflows so the project is useful without hooks.
- Introduced a thin model adapter boundary (`scripts/model_adapter.py`) for optional future integrations.
- Repositioned hooks as optional compatibility scaffolding under `integrations/claude-hooks/`.
- Added Codex repository skills in `.agents/skills/` for session summary, ingest, compile, query, and lint tasks.
- Added stable session metadata, canonical concept merging, deterministic connection generation, and fixture-based tests.
- Added a Codex-specific exported-markdown capture path for conversation ingest.

## Quick start (Codex app first)

1. Open this repository in Codex app.
2. Ask Codex to follow `AGENTS.md`.
3. Use repository skills:
   - `.agents/skills/memory-session-summary`
   - `.agents/skills/memory-ingest`
   - `.agents/skills/memory-compile`
   - `.agents/skills/memory-query`
   - `.agents/skills/memory-lint`

Typical loop:
1. Ingest recent work into `daily/`
2. Compile the daily-log corpus into `knowledge/`
3. Query before planning: use `uv run python scripts/query.py "<goal or question>" --plan-brief --explain` to pull current status, next steps, open questions, and canonical decisions
4. In Obsidian, start from `knowledge/dashboards/open-followups.md` for active goals, open work, and recent decisions
5. Lint for health and apply safe autofixes when needed

## Obsidian landing page

The primary Obsidian landing page is `knowledge/dashboards/open-followups.md`.

- `## Open Follow-Ups` shows explicit follow-up actions compiled from session `## Next Steps`
- `## Recent Decisions` shows recent explicit decision records from `knowledge/decisions/`
- pending decisions are not inferred in v1; capture them as explicit follow-up items during ingest

## Structured session summaries

When you want better compile and retrieval quality, ingest a structured session summary instead of a single sentence. Supported headings are:

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

Use `## Next Steps` for future plans you want retained in memory. Omit sections that do not apply.

Example:

```markdown
## Goal
- Start the closed beta launch.

## Summary
- Tightened the auth migration rollout plan.

## Current Status
- Two-path launch model is implemented locally.

## Decisions
- Keep `--text` backward compatible while supporting structured headings.

## Decision Links
- supersedes: [[decisions/keep-older-note]]
- implemented_by: apps/portal/lib/beta-access.ts
- blocked_by: production env setup

## Validation
- py -3 -m unittest tests.test_query -v

## Verification State
- Tests pass locally; production verification is still pending.

## Evidence
- Verified evidence excerpts now include `daily/...:line` references.

## Next Steps
- Refresh the end-to-end golden fixtures.

## Open Questions
- Which production verification step is still blocking launch?
```

## CLI/manual fallback (works without hooks)

```bash
uv sync
uv run python scripts/ingest.py --text "Worked on migration plan and codex workflow" --source-type codex-summary
uv run python scripts/ingest.py --goal "Start the closed beta" --current-status "Two-path model is implemented locally" --decision "Keep founder invites manual copy-link only" --file-touched apps/portal/lib/beta-access.ts --validation "npm --prefix apps/portal run test:policy" --next-step "Set production env and rerun launch checks"
uv run python scripts/ingest.py --file notes/session.md --session-id codex-manual-001 --title "Portal Auth Review" --source-type codex-summary
uv run python scripts/ingest.py --codex-chat-file exports/codex-chat.md --session-id codex-chat-001 --title "Codex Chat Capture"
uv run python scripts/compile.py
uv run python scripts/query.py "What changed in the migration?" --explain --evidence
uv run python scripts/query.py "What are the next steps to proceed?" --plan-brief --explain
uv run python scripts/lint.py --autofix
```

## Commands

```bash
uv run python scripts/ingest.py --text "..."           # manual session ingest; compile + lint run by default
uv run python scripts/ingest.py --text "..." --title "Auth Migration" --source-type codex-summary
uv run python scripts/ingest.py --goal "..." --current-status "..." --decision "..." --next-step "..."
uv run python scripts/ingest.py --file notes/session.md --session-id codex-manual-001
uv run python scripts/ingest.py --codex-chat-file exports/codex-chat.md --session-id codex-chat-001
uv run python scripts/ingest.py --text "..." --no-compile --no-lint
uv run python scripts/compile.py                        # rebuild KB from the daily-log corpus when changes exist
uv run python scripts/compile.py --all                  # force recompile all logs
uv run python scripts/query.py "question"               # ask KB through index-guided shortlisting
uv run python scripts/query.py "question" --explain     # show shortlist and ranking reasons
uv run python scripts/query.py "question" --evidence    # append supporting excerpts with daily-log line refs
uv run python scripts/query.py "question" --plan-brief  # planning/status view with current state, next steps, and open questions
uv run python scripts/query.py "question" --file-back   # ask + save Q&A article
uv run python scripts/lint.py                           # structural + conflict heuristic checks
uv run python scripts/lint.py --autofix                 # repair stale index rows and missing backlinks
uv run python scripts/lint.py --structural-only         # structural checks only
```

## Data model

- Daily sessions now carry stable `session_id`, `title`, `source_type`, and optional `workspace` / `repo` / `task_ref` metadata.
- Structured session summaries can also capture `goal`, `current_status`, `decision_links`, `blockers`, `files_touched`, `tests_run`, `verification_state`, `evidence_excerpts`, `open_questions`, and `date_context`.
- Exported Codex markdown chats can be ingested with `--codex-chat-file` and are stored as `Source Type: codex-chat`.
- Goal records compile into `knowledge/goals/` when sessions include explicit goal/status/question data.
- Compiled concept articles carry `concept_id`, `aliases`, `keywords`, `summary`, `source_sessions`, and `source_logs`.
- Compiled decision articles in `knowledge/decisions/` are emitted only from explicit `## Decisions` items in structured summaries and can track `supersedes`, `implemented_by`, `blocked_by`, and `superseded_by`.
- Connection articles are generated deterministically when concept co-occurrence reaches the configured threshold.

## Tests

```bash
py -3 -m unittest discover -s tests -v
```

## Optional integrations

- `integrations/claude-hooks/` contains legacy Claude lifecycle hook scripts.
- These are not required for Codex app usage.
- If unavailable in your environment, use manual ingest commands.

## Docs

- `AGENTS.md` - Codex operating spec for this repository
- `CODEX_DESKTOP_USAGE.md` - how to use the compiler from Codex desktop and how to try it in another project
- `MIGRATION_PLAN.md` - migration rationale and phased plan
- `OPERATING_GUIDE.md` - practical day-to-day usage paths and limitations
