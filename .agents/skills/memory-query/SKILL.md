---
name: memory-query
description: Retrieve answers from the markdown knowledge base using index-guided search.
---

# memory-query

Use this skill when the user asks questions about prior session knowledge.

## Steps
1. If the user is asking for a plan, next steps, blockers, open questions, or current status, run `uv run python scripts/query.py "<question>" --plan-brief --explain` before proposing a plan.
2. Otherwise run `uv run python scripts/query.py "<question>"`.
3. Use `--explain` when you need the shortlist, ranking reasons, or confidence context.
4. Use `--evidence` when verification details, code anchors, or daily-log provenance matter.
5. If the user wants persistent QA memory, run with `--file-back`.
6. Report the consulted `[[wikilinks]]`, confidence limits, and whether a decision appears superseded or still current.

## Notes
- Retrieval is deterministic and index-guided (no embeddings).
- Planning/status queries should treat the `--plan-brief` result as the default pre-plan context.
- If results are weak, suggest compiling newer daily logs first.
