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

## Trust hierarchy

1. Git and process exit codes;
2. deterministic path and command policy;
3. repository acceptance commands;
4. static review or future independent model review;
5. candidate/Agent claims.

The lower levels cannot override a failure at a higher level.

## Planned path

```text
Choice-driven UI
    ↓
Spec Compiler + Policy Gate
    ↓
Orchestrator state machine
    ↓
Independent Generator A/B/C
    ↓
Candidate Pool
    ↓
Container Sandbox + Deterministic Verifier
    ↓
Independent Reviewer
    ↓
Human Approval
    ↓
Branch / draft PR
```

The planned Agent components are intentionally absent from the current core. The verifier must remain usable with hand-written patches and an offline fixture before a model provider is connected.

## Module responsibilities

- `domain/`: immutable task contracts;
- `policy/`: fail-closed patch and scope checks;
- `sandbox/`: worktree and command execution boundaries;
- `verification/`: baseline, candidate, and evidence reports;
- `cli.py`: offline demo and JSON-producing CLI;
- `api/`: safe read-only inspection endpoints.
