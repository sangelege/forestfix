# ForestFix

[简体中文](README.zh-CN.md) · **English**

ForestFix is a verifiable patch-evaluation product for Python repositories. It turns a fixed baseline, a candidate patch, an allowed path scope, and executable acceptance commands into evidence-backed results, and exposes that workflow through a local web console.

The project deliberately separates **generation** from **trust**: an Agent may propose a patch, but only deterministic policy checks and acceptance commands can mark it as accepted.

## Current status

The repository contains a working v0.2 core:

- immutable Pydantic `TaskSpec` validation;
- fail-closed Git patch policy checks;
- denied/allowed path enforcement, including rename sources;
- test-skip/expected-failure detection;
- disposable Git worktrees with hooks disabled and cleanup checks;
- allowlisted local command execution with fixed executable resolution;
- process-group timeout handling;
- baseline reproduction and candidate verification reports;
- concurrent independent candidate evaluation;
- SQLite persistence for tasks, candidates, and reports;
- provider adapters for Hermes, Codex, and Claude print-mode CLIs;
- local branch application for approved candidates;
- a product console served by FastAPI and vanilla JavaScript;
- offline `forestfix demo` and `forestfix serve` commands.

GitHub webhooks, active pull-request creation, and a managed multi-tenant queue are still planned, not part of this core.

## Quick start

```bash
uv venv
uv pip install -e '.[dev,web]'
.venv/bin/forestfix demo
.venv/bin/forestfix serve --unsafe-local
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
```

The demo needs no API key and prints JSON containing:

- a baseline reproduction failure;
- an accepted correct patch;
- a policy-rejected test-cheating patch.

## Verify a task

Create a `TaskSpec` JSON containing an absolute `repo_path`, a 40-character lowercase `base_commit`, argument-array commands, and explicit path scope. Then run:

```bash
.venv/bin/forestfix verify \
  --spec ./task.json \
  --patch ./candidate.patch \
  --candidate-id candidate-1 \
  --output ./report.json \
  --unsafe-local
```

`--unsafe-local` is intentionally required for the current local executor. It is suitable only for trusted fixtures. A Git worktree is not a security sandbox; do not use this mode with an untrusted repository.

## Web console

Install the `web` extra, then start the product console:

```bash
.venv/bin/forestfix serve --unsafe-local
```

Open `http://127.0.0.1:8000`. The console can create a task, run the baseline, generate candidates through configured providers, inspect evidence, and apply accepted patches to a local branch.

The API includes `GET /health`, `POST /inspect-patch`, task and candidate management, provider generation, and explicit apply endpoints.

## Repository guide

- [Project plan and product design](docs/PROJECT.md)
- [Current architecture](docs/ARCHITECTURE.md)
- [Security boundaries](docs/SECURITY.md)
- [Contribution guide](CONTRIBUTING.md)

## Design rule

> First prove the verifier, then add the generator. More Agents do not compensate for missing evidence.
