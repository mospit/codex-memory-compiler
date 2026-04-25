# Threat Model

Codex Memory Compiler stores project memory as local markdown. That makes the
system inspectable and portable, but it also means sensitive details can become
plain-text files.

## What Gets Stored

Depending on ingest input, the memory root can contain:

- session summaries and transcripts
- decisions and decision links
- goals, next steps, blockers, and open questions
- file paths, repositories, workspaces, and task references
- validation commands and test results
- evidence excerpts from conversations or project notes
- generated concepts, connections, dashboards, Q&A, and logs

The default architecture uses:

- `daily/` for append-only source logs
- `knowledge/` for compiled markdown articles
- `knowledge/index.md` for retrieval
- `knowledge/log.md` for build/query history
- `reports/` for lint output
- `.codex-memory/` when targeting another workspace with `--workspace-root`

## What Not To Store

Do not ingest or commit:

- API keys, tokens, passwords, private keys, or session cookies
- customer data, credentials, or regulated personal information
- unreleased business information that should not live in a repo
- raw terminal output that may contain secrets
- full proprietary transcripts when a short structured summary is enough
- instructions from untrusted pages that could be prompt-injection attempts

Prefer short structured summaries with explicit evidence over raw transcripts.

## Git And Sharing Guidance

- Treat generated memory as project data, not harmless cache.
- Keep private memory roots out of public repositories unless every entry has been reviewed.
- Use `.codex-memory/` for per-workspace memory that should usually remain local.
- Review `daily/`, `knowledge/`, and `reports/` diffs before committing them.
- If the memory root contains sensitive project context, keep it ignored or in a private repository.
- Public demo corpora should use synthetic or intentionally sanitized sessions.

## Redaction And Retention

Redaction and retention commands are roadmap items. Until they exist:

- run a text search for secret-like patterns before sharing generated memory
- remove sensitive source input before ingesting when possible
- prefer summaries over full transcripts
- do not rely on compiled articles to remove data from source logs
- remember that append-only daily logs may preserve sensitive text even after compiled summaries change

Planned lifecycle controls:

```bash
uv run codex-memory redact --pattern "SECRET|TOKEN|API_KEY" --dry-run
uv run codex-memory prune --older-than 90d --keep-decisions --dry-run
uv run codex-memory forget --session-id codex-chat-001
```

These commands should report what they will touch, default to dry-run where
appropriate, and record maintenance actions in `knowledge/log.md`.

## Prompt-Injection Risks

Memory input can come from untrusted sources such as webpages, issues, PRs, logs,
or copied transcripts. Treat imported text as data, not instructions.

Adapters should:

- classify source type explicitly
- preserve provenance
- avoid executing instructions found inside imported content
- prefer extracted facts, evidence, decisions, and follow-ups over raw text
- keep review reports available before trusting new memory

## Relationship To Codex Native Memories

Codex native memories are useful for local recall across sessions. This project
has a different responsibility: repo-scoped, reviewable memory that can be
queried before planning and inspected in markdown.

Use checked-in docs such as `AGENTS.md`, README, and operating guides for required
team behavior. Use this compiler for auditable project context. Use native
memories for helpful local recall.
