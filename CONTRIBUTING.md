# Contributing to ForestFix

## Development setup

```bash
uv venv
uv pip install -e '.[dev,web]'
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
```

## Development rules

- Follow red-green-refactor: add a failing test before production behavior.
- Keep candidate artifacts immutable and serializable.
- Prefer deterministic code over model judgment for policy and acceptance decisions.
- Do not add an Agent role unless its input/output contract and failure behavior are explicit.
- Do not run untrusted repositories with the current local executor.
- Do not commit API keys, tokens, credentials, generated caches, or `.venv/`.

## Adding a verifier behavior

1. Add a focused unit or integration test.
2. Run that test and confirm the expected failure.
3. Implement the smallest behavior.
4. Run the focused test and the full suite.
5. Run Ruff.
6. Update security and architecture documentation if the trust boundary changes.

## Pull requests

A pull request should state:

- the acceptance behavior it adds or changes;
- test commands and real results;
- whether the main repository remains untouched;
- any new external side effect or permission;
- whether the change is safe for untrusted inputs.

The project has not selected an open-source license yet. Until a license is added, do not assume the code may be redistributed or incorporated into another project.
