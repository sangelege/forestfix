# Changelog

## 0.2.0 — Product console and provider orchestration

- Added provider orchestration for Hermes, Codex, and Claude print-mode CLIs.
- Added SQLite candidate persistence and task lifecycle statuses.
- Added automatic executor selection between Docker and explicit trusted local mode.
- Added a FastAPI + vanilla JavaScript product console for task creation, baseline reproduction, provider generation, evidence review, and local branch application.
- Added `forestfix serve` and safe branch application for accepted candidates.
- Hardened local execution for Windows, including Python alias resolution and descendant process termination.
- Kept the existing deterministic verifier as the trust boundary.

## 0.1.0 — Initial core

- Added immutable `TaskSpec` validation with explicit acceptance commands and path scope.
- Added fail-closed Git patch inspection, rename-path checks, and basic test-cheating detection.
- Added disposable Git worktrees with hook suppression, timeouts, and cleanup verification.
- Added explicit trusted-fixture local executor with executable resolution and process-group timeouts.
- Added baseline reproduction and candidate verification reports.
- Candidate verification now reruns the reproduced failure before accepting any unrelated acceptance command.
- Added concurrent independent candidate evaluation.
- Added offline CLI demo and `forestfix verify` JSON workflow.
- Added read-only FastAPI health and patch-inspection endpoints.
- Added fixture-based unit, integration, security-boundary, and packaging tests.

### Known limitations

- No LLM provider or Agent generator is connected yet.
- No persistent task/artifact store exists yet.
- Local execution is not a security sandbox and requires `--unsafe-local`.
- Container-backed execution, GitHub webhooks, pull-request creation, and active suggestions are planned work.
- No open-source license has been selected yet.
