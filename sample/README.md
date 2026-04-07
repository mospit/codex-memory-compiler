# Sample Demo Corpus

Use this fixture to validate the deterministic pipeline without touching your real notes.

## Run end-to-end demo

```bash
uv run python scripts/run_sample.py
```

The script will:
1. Create an isolated temporary workspace.
2. Ingest fixture context files from `sample/demo-context/`.
3. Compile logs into `knowledge/`.
4. Run a sample query.
5. Run structural lint.

It prints the temporary workspace path so you can inspect generated files.
