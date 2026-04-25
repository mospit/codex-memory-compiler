# Roadmap

Codex Memory Compiler should be the repo-visible memory layer for project
decisions, status, evidence, and next actions. It should complement Codex native
memories by producing auditable markdown artifacts that can be reviewed before
planning.

## Priority Order

| Priority | Change | Why |
| ---: | --- | --- |
| 1 | Fix positioning and docs | Native Codex memories exist, so this project needs a sharper role. |
| 2 | Add capture adapters | Manual ingest is the biggest adoption blocker. |
| 3 | Add review/diff workflow | Trust is the core product problem for persistent memory. |
| 4 | Add prune/forget/redact | Memory without lifecycle controls becomes risky. |
| 5 | Add hybrid retrieval | Index-only retrieval will hit limits as the KB grows. |
| 6 | Add demo corpus and releases | The repo needs a clearer "try this now" surface. |

## Phase 1: Positioning And Docs

- Present the project as a repo-scoped, markdown-first memory compiler.
- State clearly that it complements Codex native memories instead of replacing them.
- Keep Codex capture limitations explicit: there is no supported Codex-native session-end hook in this repository today.
- Document three paths: solo dogfood, Codex app, and future automation.
- Add privacy, retention, redaction, and sharing guidance.

## Phase 2: Capture Adapters

Planned adapters should be explicit imports, not hidden background capture:

- `codex-memory ingest-git --since HEAD~10`
- `codex-memory ingest-pr --file pr.md`
- `codex-memory ingest-issue --file issue.md`
- `codex-memory ingest-codex-memory --path ~/.codex/memories --read-only`
- `codex-memory ingest-transcript --format codex|claude|raw`

Each adapter should emit the same structured daily-log sections used by manual
ingest: goal, current status, decisions, decision links, files, validation,
evidence, next steps, and open questions.

## Phase 3: Review And Diff Workflow

Memory changes should be reviewable before they become trusted project context.

Useful outputs:

- new decisions
- likely superseded decisions
- changed summaries
- new open questions
- stale or deleted links
- source logs not referenced by compiled articles
- files and validation evidence tied to decisions

The first version can be a dry-run report. Later versions can generate a memory
PR or structured review bundle.

## Phase 4: Lifecycle Controls

Add safe lifecycle commands before memory volume grows:

```bash
uv run codex-memory prune --older-than 90d --keep-decisions --dry-run
uv run codex-memory forget --session-id codex-chat-001
uv run codex-memory redact --pattern "SECRET|TOKEN|API_KEY" --dry-run
```

These commands should default to dry-run or explicit confirmation, record their
effects in `knowledge/log.md`, and avoid rewriting historical source logs unless
the user explicitly chooses that behavior.

## Phase 5: Hybrid Retrieval

Keep `knowledge/index.md` as the canonical catalog, then add optional retrieval
layers behind the same CLI:

1. index shortlist
2. SQLite FTS5 or BM25 lexical search
3. optional semantic rerank
4. article-body scoring
5. source-backed evidence excerpts

The deterministic markdown index should remain usable even when optional search
indexes are absent.

## Phase 6: Product Surface

- Add a polished demo corpus that shows before/after value in under two minutes.
- Add a decision dashboard answering what was decided, what superseded what, what is blocked, what evidence supports decisions, and what Codex should ask before continuing.
- Publish tagged releases once the CLI/docs path is stable.
