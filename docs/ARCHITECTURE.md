# Current Architecture

## Implemented path

```text
TaskSpec JSON
    ↓
Policy inspection ──→ reject malformed, out-of-scope, or test-cheating patch
    ↓
Git worktree (detached, hooks disabled)
    ↓
git apply --index
    ↓
actual staged paths checked again
    ↓
allowlisted command executor
    ↓
BaselineReport / VerificationReport JSON
```

`VerificationPipeline.verify_candidate` is the trust boundary for a candidate. It never edits the main repository. Every candidate receives a separate worktree, and `verify_candidates` evaluates candidates independently with deterministic result ordering.

The product console adds a generation path before this trust boundary:

```text
TaskSpec JSON
    ↓
Baseline reproduction
    ↓
Provider A / B / C (Hermes, Codex, Claude)
    ↓
Candidate patch
    ↓
Deterministic verification
    ↓
Human approval → local branch apply
```

## Trust hierarchy

1. Git and process exit codes;
2. deterministic path and command policy;
3. repository acceptance commands;
4. static review or future independent model review;
5. candidate/Agent claims.

The lower levels cannot override a failure at a higher level.

## Remaining path

```text
GitHub webhook / CI trigger
    ↓
Task suggestion
    ↓
Human approval
    ↓
Draft pull request
    ↓
No automatic merge
```

The verifier remains usable with hand-written patches and an offline fixture before any remote side effect is enabled.

## Module responsibilities

- `domain/`: immutable task contracts;
- `policy/`: fail-closed patch and scope checks;
- `sandbox/`: worktree and command execution boundaries;
- `verification/`: baseline, candidate, and evidence reports;
- `cli.py`: offline demo and JSON-producing CLI;
- `api/`: product console and task/candidate endpoints.
- `orchestration/`: provider-to-verification product service.
- `storage/`: task, candidate, and report persistence.
