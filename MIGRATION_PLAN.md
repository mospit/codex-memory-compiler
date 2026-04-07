# Codex Migration Plan

## Objective
Migrate this repository from a Claude-specific implementation to a Codex-first implementation while preserving the markdown memory-compiler architecture:
- `daily/` as immutable conversation logs
- `knowledge/` as compiled articles (`concepts/`, `connections/`, `qa/`)
- index-guided retrieval via `knowledge/index.md`
- append-only operational history in `knowledge/log.md`

## Claude-Specific Assumptions Identified (Audit)

### Configuration and lifecycle coupling
- `hooks/session-start.py` assumes Claude SessionStart hook payload and output format.
- `hooks/session-end.py` assumes Claude SessionEnd hook payload, transcript JSONL format, and lifecycle timing.
- `hooks/pre-compact.py` assumes Claude PreCompact hook and Claude-specific bug behavior.
- `README.md` currently describes Claude hooks as the primary UX and setup path.
- `AGENTS.md` currently documents Claude Code hooks and Claude Agent SDK as core architecture.

### Model/runtime dependency coupling
- `pyproject.toml` depends on `claude-agent-sdk`.
- `scripts/compile.py` imports and uses `claude_agent_sdk.query()` with Claude-specific options/tools.
- `scripts/query.py` imports and uses `claude_agent_sdk.query()`.
- `scripts/flush.py` imports and uses `claude_agent_sdk.query()` and Claude recursion env guard conventions.
- `scripts/lint.py` contradiction check imports and uses `claude_agent_sdk.query()`.

### Claude-branding and assumptions in project language
- Project naming and quick-start copy in `README.md` is Claude-first.
- Operational notes assume Claude credentials and Claude subscription cost model.

## Migration Principles
1. Preserve the content model and file architecture.
2. Make Codex app the primary operator interface.
3. Keep hooks optional (progressive enhancement), not required.
4. Provide robust manual/scripted ingest -> compile -> query workflow.
5. Isolate model-dependent behavior behind a thin adapter boundary.
6. Favor deterministic file plumbing and validation logic.

## Phases

## Phase 1 (Minimum viable Codex-app-usable core)
- Introduce a model adapter boundary in `scripts/`.
- Remove hard dependency on Claude SDK from runtime path.
- Refactor core scripts:
  - `flush`/ingest: deterministic extraction fallback from transcripts/context.
  - `compile`: deterministic article update plumbing and index/log updates.
  - `query`: deterministic index-guided retrieval fallback.
  - `lint`: structural checks by default; contradiction check optional and adapter-based.
- Ensure all core scripts function without hooks.

## Phase 2 (Codex-native workflow)
- Replace AGENTS with Codex-oriented operational instructions.
- Add `.agents/skills/` for Codex app workflows:
  - memory-ingest
  - memory-compile
  - memory-query
  - memory-lint
- Rewrite README for Codex app happy path + cloud context.
- Add `OPERATING_GUIDE.md` with:
  - best experience path
  - works-everywhere fallback
  - limitations/platform notes

## Phase 3 (Progressive enhancement + compatibility)
- Keep Claude hooks isolated as optional legacy integration (documented, not required).
- Clearly mark non-portable hook assumptions and provide fallback commands.
- Add sanity-check command set and update usage docs.

## Acceptance Criteria
- Repository no longer requires Claude-specific SDK/tooling to provide value.
- Codex app user can open repo and follow AGENTS + README to operate system.
- Core architecture remains markdown-first and index-driven.
- Hooks are optional enhancement, not prerequisite.
- Documentation is explicit about supported flows and limitations.
