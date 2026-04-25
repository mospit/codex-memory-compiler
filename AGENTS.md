# AGENTS.md - Codex Memory Compiler Operating Spec

This repository is a **repo-scoped, markdown-first memory compiler** for
decisions, goals, follow-ups, and project evidence.

It complements Codex native memories. Native memories are useful local recall;
this repository owns the reviewable, versioned, inspectable knowledge artifacts
that can be committed, queried, linted, and reviewed with the project.

## Purpose
Compile project work into a markdown knowledge base while preserving the
original architecture:
- `daily/` = immutable source logs
- `knowledge/` = compiled articles
- `knowledge/index.md` = primary retrieval catalog
- `knowledge/log.md` = append-only build/query history

The compiler should be honest about capture limits. Codex-native session-end
hooks are not currently supported here; use manual ingest, exported transcripts,
or future explicit source adapters.

## Codex-First Workflow

### Best experience (Codex app)
1. Open the repo in Codex app.
2. Ask Codex to use the repository skills in `.agents/skills/`:
   - `memory-ingest`
   - `memory-session-summary`
   - `memory-compile`
   - `memory-query`
   - `memory-lint`
3. Before proposing a plan, next steps, or current-status summary, run `memory-query` first and prefer `uv run python scripts/query.py "<question>" --plan-brief --explain`.
4. Keep changes small and commit after each logical phase.

### Works-everywhere fallback (no hooks required)
```bash
uv run codex-memory ingest --root . --text "Worked on auth migration and fixed token bug"
uv run codex-memory ingest --root . --codex-chat-file exports/codex-chat.md --session-id codex-chat-001
uv run codex-memory compile --root .
uv run codex-memory query --root . "What did I decide about auth migration?"
uv run codex-memory lint --root . --structural-only
```

## Architecture Contracts

### Daily logs (`daily/`)
- Append-only session history.
- Each session entry should include a stable `session_id`, a human title, and a structured `source_type`.
- Never rewrite historical entries unless explicitly asked.

### Compiled knowledge (`knowledge/`)
- Concept articles in `knowledge/concepts/`.
- Connection articles in `knowledge/connections/`.
- Filed Q&A in `knowledge/qa/`.
- Every article should include YAML frontmatter with at least:
  - `title`
  - `summary`
  - `source_sessions`
  - `source_logs`
  - `created`
  - `updated`
  - `managed_by` for generated concept/connection/Q&A files

### Index-driven retrieval
- Read `knowledge/index.md` first.
- Shortlist candidate articles from the index before opening article bodies.
- Prefer `[[wikilinks]]` in answers and article cross-references.

## Scripts and Responsibilities
- `scripts/ingest.py`: manual ingest entrypoint (Codex-friendly fallback) that appends to daily logs, compiles and lints by default, and supports exported Codex markdown chat capture.
- `scripts/flush.py`: context-to-daily-log ingestion (used by manual flow or optional integrations).
- `scripts/compile.py`: corpus-wide deterministic compile from daily logs into canonical concepts + connections.
- `scripts/query.py`: deterministic index-guided retrieval with shortlist explanation and optional file-back into `knowledge/qa/`.
- `scripts/lint.py`: structural health checks, maintenance heuristics, and safe autofixes.
- `scripts/model_adapter.py`: thin boundary for optional future model integrations.

## Optional Integrations
Claude-specific hook examples are isolated under:
- `integrations/claude-hooks/`

These are **optional compatibility scaffolding**, not core requirements.

Future adapters should be explicit, reviewable source imports rather than hidden
capture paths. Planned sources include git commits, PR descriptions, issue
comments, exported Codex chats, transcript files, and read-only Codex memory
imports.

## Editing Guidelines
- Preserve markdown knowledge model and directory contracts.
- Prefer deterministic file operations and explicit index/log updates.
- Keep concept identity stable through `concept_id` rather than raw session headings.
- Avoid hidden magic; prioritize maintainability for a solo developer.
- Keep diffs focused and easy to review.
- Do not present this project as a replacement for Codex native memories.
- Put durable product direction in checked-in docs such as `docs/roadmap.md`.
- Put privacy, retention, redaction, and sharing guidance in `docs/threat-model.md`.

## Definition of Done for Changes
- Value is available without provider-specific hooks or SDKs.
- Codex app users can operate the system from AGENTS + README alone.
- `daily/ -> knowledge/` pipeline remains intact.
