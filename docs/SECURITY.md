# Security Boundaries

## Important current limitation

ForestFix v0.1 is **trusted-input-only** when using `CommandExecutor` with `allow_unsafe_local=True`.

A Git worktree provides filesystem separation between candidates, but it is not an operating-system sandbox. The current local executor does not isolate:

- network access;
- host filesystem access outside the worktree;
- process visibility;
- kernel resources;
- repository build scripts or dependencies;
- output memory before it is collected.

Do not run this mode against an untrusted repository, malicious patch, or production checkout.

## Current safeguards

- local execution requires explicit `allow_unsafe_local=True`;
- executable names must be allowlisted and are resolved once from a fixed system PATH;
- command arguments are passed as an array, never through a shell;
- Git hooks are disabled while creating worktrees and applying patches;
- candidate IDs reject path-like characters;
- TaskSpec paths reject absolute paths, backslashes, NUL bytes, and `..` components;
- malformed patches are rejected rather than treated as empty changes;
- old and new paths are checked for renames;
- process groups are killed on timeout;
- cleanup failures are surfaced;
- the main repository is not modified by candidate verification.

## Required before untrusted execution

A production executor must provide all of the following at the OS/container layer:

- rootless container or equivalent sandbox;
- no network by default;
- read-only source mount and disposable writable workspace;
- no host credentials, home directory, Docker socket, or SSH keys;
- CPU, memory, process, disk, log, and wall-clock limits;
- process-tree cleanup;
- explicit image and dependency provenance;
- verification that the candidate workspace and sandbox are gone after execution.

The policy layer is not a replacement for these controls.

## Reporting a security issue

Do not include secrets or malicious payloads in a public issue. Contact the repository owner privately with reproduction steps, affected commit, impact, and a minimal safe proof. Until a container-backed executor exists, treat any report involving arbitrary repository execution as expected out-of-scope behavior rather than evidence that local mode is safe.
