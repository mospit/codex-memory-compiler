---
name: memory-query
description: Retrieve answers from the markdown knowledge base using index-guided search.
---

# memory-query

Use this skill when the user asks questions about prior session knowledge.

## Steps
1. Run `uv run python scripts/query.py "<question>"`.
2. Use `--explain` when you need the shortlist, ranking reasons, or confidence context.
3. If the user wants persistent QA memory, run with `--file-back`.
4. Report the consulted `[[wikilinks]]` and confidence limits.

## Notes
- Retrieval is deterministic and index-guided (no embeddings).
- If results are weak, suggest compiling newer daily logs first.
