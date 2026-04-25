---
managed_by: codex-memory-compiler
schema_version: 2
title: Keep the shared auth redirect guard during migration.
decision_id: keep-shared-authentication-redirect-guard-during-migration
summary: Keep the shared auth redirect guard during migration.
current_status: 
verification_state: 
supersedes: []
implemented_by: []
blocked_by: []
superseded_by: []
open_questions: []
files_touched:
  - "apps/portal/src/auth/redirect.ts"
tests_run:
  - "Verified redirect guard behavior in staging."
  - "Compared migration notes against the current API contract."
source_sessions:
  - "s1"
  - "s2"
source_logs:
  - "daily/2026-04-08.md"
source_types:
  - "codex-summary"
created: 2026-04-08
updated: 2026-04-08
---

# Keep the shared auth redirect guard during migration.

Keep the shared auth redirect guard during migration.

## Decision
- Keep the shared auth redirect guard during migration.

## Files
- apps/portal/src/auth/redirect.ts

## Validation
- Verified redirect guard behavior in staging.
- Compared migration notes against the current API contract.

## Rationale / Evidence
- daily/2026-04-08.md:22 / `s1` (codex-summary): Keep the shared auth redirect guard during migration.
- daily/2026-04-08.md:34 / `s1` (codex-summary): Confirmed redirect requests resolve through the shared guard path.
- daily/2026-04-08.md:31 / `s1` (codex-summary): Verified redirect guard behavior in staging.
- daily/2026-04-08.md:55 / `s2` (codex-summary): Keep the shared auth redirect guard during migration.
- daily/2026-04-08.md:62 / `s2` (codex-summary): Confirmed the redirect guard still matches the shared contract.
- daily/2026-04-08.md:59 / `s2` (codex-summary): Compared migration notes against the current API contract.

## Related Concepts
- [[concepts/authentication-migration]] - Mentioned alongside this decision in 2 session(s)
- [[concepts/api-portal]] - Mentioned alongside this decision in 1 session(s)

## Sources
- [[daily/2026-04-08.md]]
