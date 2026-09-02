"""The deterministic verification pipeline."""

import hashlib
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path

from forestfix.domain.task_spec import TaskSpec
from forestfix.policy.patch_policy import inspect_patch, inspect_paths
from forestfix.sandbox.executor import CommandRunner
from forestfix.sandbox.worktrees import GitWorktreeManager
from forestfix.verification.reports import BaselineReport, CommandEvidence, VerificationReport


class VerificationPipeline:
    def __init__(self, spec: TaskSpec, executor: CommandRunner, worktree_root: Path) -> None:
        self.spec = spec
        self.executor = executor
        self.worktrees = GitWorktreeManager(spec.repo_path, worktree_root)

    def reproduce_baseline(self) -> BaselineReport:
        candidate_id = "baseline-" + re.sub(r"[^A-Za-z0-9._-]", "-", self.spec.task_id)
        with self.worktrees.candidate(candidate_id, self.spec.base_commit) as worktree:
            result = self.executor.run(
                self.spec.reproduction_command,
                cwd=worktree,
                timeout_seconds=self.spec.timeout_seconds,
            )
        return BaselineReport(
            base_commit=self.spec.base_commit,
            reproduced=result.exit_code != 0 and not result.timed_out,
            command=CommandEvidence.from_result(result),
        )

    def verify_candidate(self, candidate_id: str, patch: str) -> VerificationReport:
        patch_sha256 = hashlib.sha256(patch.encode()).hexdigest()
        policy_findings = inspect_patch(
            patch,
            allowed_patterns=self.spec.allowed_paths,
            denied_patterns=self.spec.denied_paths,
        )
        if policy_findings:
            return VerificationReport(
                candidate_id=candidate_id,
                patch_sha256=patch_sha256,
                accepted=False,
                stage="policy_rejected",
                policy_findings=tuple(asdict(finding) for finding in policy_findings),
            )

        with self.worktrees.candidate(candidate_id, self.spec.base_commit) as worktree:
            applied = subprocess.run(
                [
                    "git",
                    "-c",
                    "core.hooksPath=/dev/null",
                    "-c",
                    "core.autocrlf=false",
                    "apply",
                    "--index",
                    "--whitespace=error",
                    "-",
                ],
                cwd=worktree,
                input=patch.encode("utf-8"),
                check=False,
                capture_output=True,
                timeout=self.worktrees.git_timeout_seconds,
            )
            if applied.returncode != 0:
                apply_error = applied.stderr.decode("utf-8", errors="replace").strip()
                return VerificationReport(
                    candidate_id=candidate_id,
                    patch_sha256=patch_sha256,
                    accepted=False,
                    stage="apply_failed",
                    apply_error=apply_error or "git apply failed",
                )

            actual_paths = self._actual_paths(worktree)
            scope_findings = inspect_paths(
                set(actual_paths),
                allowed_patterns=self.spec.allowed_paths,
                denied_patterns=self.spec.denied_paths,
            )
            if scope_findings:
                return VerificationReport(
                    candidate_id=candidate_id,
                    patch_sha256=patch_sha256,
                    accepted=False,
                    stage="policy_rejected",
                    policy_findings=tuple(asdict(finding) for finding in scope_findings),
                    actual_paths=actual_paths,
                )

            evidence: list[CommandEvidence] = []
            reproduction = self.executor.run(
                self.spec.reproduction_command,
                cwd=worktree,
                timeout_seconds=self.spec.timeout_seconds,
            )
            evidence.append(CommandEvidence.from_result(reproduction))
            if reproduction.exit_code != 0 or reproduction.timed_out:
                return VerificationReport(
                    candidate_id=candidate_id,
                    patch_sha256=patch_sha256,
                    accepted=False,
                    stage="verification_failed",
                    actual_paths=actual_paths,
                    commands=tuple(evidence),
                )

            for command in self.spec.acceptance_commands:
                result = self.executor.run(
                    command,
                    cwd=worktree,
                    timeout_seconds=self.spec.timeout_seconds,
                )
                evidence.append(CommandEvidence.from_result(result))
                if result.exit_code != 0 or result.timed_out:
                    return VerificationReport(
                        candidate_id=candidate_id,
                        patch_sha256=patch_sha256,
                        accepted=False,
                        stage="verification_failed",
                        actual_paths=actual_paths,
                        commands=tuple(evidence),
                    )

        return VerificationReport(
            candidate_id=candidate_id,
            patch_sha256=patch_sha256,
            accepted=True,
            stage="accepted",
            actual_paths=actual_paths,
            commands=tuple(evidence),
        )

    def verify_candidates(self, candidates: dict[str, str]) -> tuple[VerificationReport, ...]:
        """Evaluate independent candidates concurrently with deterministic output order."""
        if not candidates:
            raise ValueError("at least one candidate is required")
        if len(candidates) > self.spec.candidate_count:
            raise ValueError("candidate count exceeds the TaskSpec budget")
        with ThreadPoolExecutor(max_workers=len(candidates)) as pool:
            futures = {
                candidate_id: pool.submit(self.verify_candidate, candidate_id, patch)
                for candidate_id, patch in candidates.items()
            }
            return tuple(futures[candidate_id].result() for candidate_id in sorted(futures))

    def _actual_paths(self, worktree: Path) -> tuple[str, ...]:
        result = subprocess.run(
            ["git", "diff", "--cached", "--no-renames", "--name-only", "-z"],
            cwd=worktree,
            check=True,
            capture_output=True,
            timeout=self.worktrees.git_timeout_seconds,
        )
        return tuple(sorted(path for path in result.stdout.decode().split("\x00") if path))
