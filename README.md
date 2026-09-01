# ForestFix

ForestFix evaluates candidate patches in isolated Git worktrees and keeps only candidates backed by executable evidence.

The repository is currently implementing Phase 0: deterministic task specifications, policy checks, isolated execution, and verification reports before any LLM generator is connected.

## Documentation

- [Product and architecture plan](docs/PROJECT.md)

> [!WARNING]
> The current local command executor is only intended for trusted Phase 0 fixtures. Do not run untrusted repositories until the container-backed executor is implemented.
