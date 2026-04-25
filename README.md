# Codex Memory Compiler

Codex Memory Compiler is a repo-scoped, markdown-first memory compiler for
decisions, goals, follow-ups, and project evidence. It complements Codex native
memories by producing reviewable, versioned knowledge artifacts inside your repo
or `.codex-memory/`.

It is not a replacement for native Codex memories. Treat Codex memories as a
helpful local recall layer, and use this project when the memory needs to be
auditable, inspectable in git, queryable before planning, and easy to review in
Obsidian.

The compiler keeps the original memory-compiler architecture intact:
- `daily/` as append-only source logs
- `knowledge/` as compiled concept, connection, decision, goal, and Q&A articles
- `knowledge/index.md` as the retrieval catalog
- `knowledge/log.md` as the append-only compile/query history

## Product Role

- Repo-scoped memory: knowledge lives with the project it describes.
- Markdown-first artifacts: outputs are inspectable, diffable, and Obsidian-friendly.
- Explicit decisions: decision pages come only from explicit `## Decisions` items.
- Query-before-planning: agents should retrieve current status, next steps, open questions, and canonical decisions before proposing work.
- Provider-light workflow: the supported CLI is `codex-memory`, available through `uv run codex-memory`.
- Repo-local Codex skills live under `.agents/skills/`, including session summary, ingest, compile, query, and lint tasks.
- Exported Codex markdown chats and structured session summaries can be ingested directly.
- Compile, query, and lint remain deterministic and markdown-native.
- Optional compatibility hooks live under `integrations/claude-hooks/`.

## Usage Paths

### Solo Dogfood Path

Use this when you want to run the compiler yourself from a terminal.

```bash
uv sync
uv run codex-memory --help
uv run codex-memory init --workspace-root D:/projects/other-project
uv run codex-memory ingest --workspace-root D:/projects/other-project --text "Worked on auth migration and fixed token bug" --source-type codex-summary
uv run codex-memory query --workspace-root D:/projects/other-project "What did I decide about auth migration?" --plan-brief --explain
uv run codex-memory lint --workspace-root D:/projects/other-project --structural-only
```

Use `--root .` when running inside this repository so the active memory root is
explicit even if your shell has `KB_ROOT_DIR` set elsewhere:

```bash
uv run codex-memory compile --root .
uv run codex-memory query --root . "What does this memory compiler know already?" --explain
```

### Codex App Path

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
3. Query before planning: use `uv run codex-memory query --root . "<goal or question>" --plan-brief --explain` to pull current status, next steps, open questions, and canonical decisions
4. In Obsidian, start from `knowledge/dashboards/open-followups.md` for active goals, open work, and recent decisions
5. Lint for health and apply safe autofixes when needed

### Automation Path

Automation is a roadmap item, not a supported promise today. The intended shape
is to ingest structured sources such as git commits, PR descriptions, issue
comments, exported Codex chats, and read-only Codex memory files through explicit
adapters. Until those adapters exist, use `codex-memory ingest` with structured
session summaries or exported markdown transcripts.

## Obsidian Landing Page

The primary Obsidian landing page is `knowledge/dashboards/open-followups.md`.

- `## Open Follow-Ups` shows explicit follow-up actions compiled from session `## Next Steps`
- `## Recent Decisions` shows recent explicit decision records from `knowledge/decisions/`
- Pending decisions are not inferred in v1; capture them as explicit follow-up items during ingest

## Structured Session Summaries

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

## CLI Commands

```bash
uv run codex-memory init --workspace-root D:/projects/other-project
uv run codex-memory ingest --root . --text "Worked on memory compiler docs." --source-type codex-summary
uv run codex-memory ingest --root . --goal "Start the closed beta" --current-status "Two-path model is implemented locally" --decision "Keep founder invites manual copy-link only" --file-touched apps/portal/lib/beta-access.ts --validation "npm --prefix apps/portal run test:policy" --next-step "Set production env and rerun launch checks"
uv run codex-memory ingest --root . --file notes/session.md --session-id codex-manual-001 --title "Portal Auth Review" --source-type codex-summary
uv run codex-memory ingest --root . --codex-chat-file exports/codex-chat.md --session-id codex-chat-001 --title "Codex Chat Capture"
uv run codex-memory compile --root .
uv run codex-memory compile --root . --all
uv run codex-memory query --root . "What did I decide about the workflow?" --explain
uv run codex-memory query --root . "What changed this week?" --explain --evidence
uv run codex-memory query --root . "What are the next steps to proceed?" --plan-brief --explain
uv run codex-memory query --root . "What changed this week?" --file-back
uv run codex-memory lint --root . --structural-only
uv run codex-memory lint --root . --autofix
```

Legacy script entrypoints remain available as compatibility shims:

```bash
uv run python scripts/ingest.py --text "Worked on migration plan and codex workflow" --source-type codex-summary
uv run python scripts/query.py "What changed in the migration?" --explain --evidence
uv run python scripts/lint.py --autofix
```

## Mini Guides

### Capture a short session in this repo

```bash
uv run codex-memory ingest --root . --text "Validated the packaged codex-memory CLI in this repository and updated the README." --title "CLI Validation" --source-type codex-summary
uv run codex-memory compile --root .
```

### Ingest an exported Codex chat

```bash
uv run codex-memory ingest --root . --codex-chat-file exports/codex-chat.md --session-id codex-chat-001 --title "Codex Chat Capture"
```

### Ask the compiled knowledge base a question

```bash
uv run codex-memory query --root . "What did we decide about using git commits as an ingest source?" --explain
```

### Use this checkout with another project

```bash
uv run codex-memory init --workspace-root D:/projects/other-project
uv run codex-memory ingest --workspace-root D:/projects/other-project --text "Worked on auth migration." --title "Auth Migration" --source-type codex-summary --workspace "D:/projects/other-project" --repo "owner/other-project"
uv run codex-memory compile --workspace-root D:/projects/other-project
uv run codex-memory query --workspace-root D:/projects/other-project "What did I do in the other project?" --explain
```

## Root Targeting

The CLI resolves the memory root in this order:

1. `--root PATH`
2. `--workspace-root PATH` which maps to `<workspace>/.codex-memory`
3. `KB_ROOT_DIR`
4. The current working directory's `.codex-memory`

Practical guidance:
- Use `--root .` when you want this repository itself to be the memory root.
- Use `--workspace-root PATH` when you want a separate project's memory under its own `.codex-memory/`.
- Prefer explicit flags over ambient `KB_ROOT_DIR` when you are switching between projects.

## Data Model

- Daily sessions carry stable `session_id`, `title`, `source_type`, and optional `workspace` / `repo` / `task_ref` metadata.
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

## Optional Integrations

- `integrations/claude-hooks/` contains compatibility-only Claude lifecycle hook scripts.
- These are not required for Codex app usage.
- The supported fallback path is the `codex-memory` CLI.
- Automatic Codex session-end capture is not supported by this repository today.
- See `docs/roadmap.md` for planned source adapters and `docs/threat-model.md` for storage and sharing guidance.

## Docs

- `AGENTS.md` - operating spec for this repository
- `CODEX_DESKTOP_USAGE.md` - Codex desktop workflow notes
- `OPERATING_GUIDE.md` - practical usage paths and limitations
- `docs/roadmap.md` - product priorities and future work
- `docs/threat-model.md` - privacy, retention, redaction, and git safety notes
- `MIGRATION_PLAN.md` - migration rationale and phased plan
