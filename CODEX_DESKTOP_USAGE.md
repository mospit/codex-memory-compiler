# Codex Desktop Usage Guide

This project is designed to be used from the Codex desktop app as a repo-local,
auditable memory compiler. It complements Codex native memories by producing
markdown artifacts for decisions, goals, follow-ups, evidence, and status that
can be reviewed with the project.

## Recommended Flow In This Repo

1. Open `D:/projects/product/codex-memory-compiler` in Codex desktop.
2. Start by telling Codex:

```text
Read AGENTS.md and use the repository skills memory-session-summary, memory-ingest, memory-compile, memory-query, and memory-lint for this repo.
```

3. Use the normal loop:

```text
Use memory-ingest to save this session as a codex-summary titled "Dogfood Walkthrough".
Use memory-compile to rebuild the knowledge base.
Use memory-query to answer: How am I using the codex memory compiler in this repo?
Use memory-lint and summarize any issues.
```

## Good Prompt Examples

Save a short session summary:

```text
Read AGENTS.md. Use memory-ingest to save this session: I tested codex-memory-compiler on itself and verified ingest, compile, query, and lint.
```

Save a structured session summary:

```text
Read AGENTS.md. Use memory-session-summary and memory-ingest to save this session with sections for Summary, Decisions, Validation, Evidence, and Next Steps.
```

Compile and query:

```text
Use memory-compile, then use memory-query to answer: What did I decide about the memory compiler workflow? Include supporting evidence excerpts.
```

Maintenance:

```text
Use memory-lint and apply safe autofixes if needed.
```

## Important Limitation

This repo does not currently include a supported Codex-native session-end hook.
In Codex desktop, memory capture is manual unless you export a chat to markdown
and ingest that file explicitly.

That limitation is intentional in the current product shape: capture should be
explicit and reviewable until source adapters exist for git commits, PRs, issues,
transcripts, or read-only Codex memory imports.

For transcript-style capture:

```powershell
uv run codex-memory ingest --root . --codex-chat-file exports/codex-chat.md --session-id codex-chat-001 --title "Codex Chat Capture"
```

## Is It Installed On This Machine?

Not as a machine-wide tool.

What exists on this machine right now is:

- this repository
- its Python package and CLI entry point
- its Python scripts under `scripts/`
- its repo-local Codex skills under `.agents/skills/`

There is no globally installed `codex-memory-compiler` command. Use
`uv run codex-memory` from this checkout or from a project that has installed
the package.

## Trying It On Another Project

There are two workable paths.

### Option A: Copy The Memory Compiler Into The Target Project

This is the best fit if you want the same Codex desktop experience inside
another repo.

Bring these files into the target project:

- `AGENTS.md`
- `.agents/skills/`
- `scripts/`
- `codex_memory_compiler/`
- `pyproject.toml`

Then in the target project:

```powershell
uv sync
```

Open that target project in Codex desktop and use the same prompts as above.

This works because the memory compiler is currently repo-local, not globally
installed.

### Option B: Reuse This Checkout And Point It At Another Project

This is useful if you want to try the compiler on another project without
copying files yet.

Initialize the memory root first:

```powershell
uv run codex-memory init --workspace-root D:/projects/other-project
```

From `D:/projects/product/codex-memory-compiler`, set `KB_ROOT_DIR` to a memory
folder for the other project:

```powershell
$env:KB_ROOT_DIR = "D:/projects/other-project/.codex-memory"
uv run codex-memory ingest --text "Worked on auth migration." --title "Auth Migration" --source-type codex-summary --workspace "D:/projects/other-project" --repo "owner/other-project"
uv run codex-memory compile
uv run codex-memory query "What did I do in the other project?" --explain --evidence
```

This keeps the compiler code in this repo, but stores the memory database under
the other project's `.codex-memory/` folder.

Important: Option B is a CLI/manual workflow. Codex desktop in the other project
will not automatically have this repo's skills unless you copy them into that
project or install an equivalent global skill setup.

## Recommendation

If you want to dogfood quickly, use Option B first.

If you want Codex desktop to feel native inside another repo, use Option A and
keep the memory compiler files in that repo.

Before committing or sharing generated memory artifacts, read
`docs/threat-model.md`.
