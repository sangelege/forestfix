"""Application service that connects generators, verifiers, and persistence."""

import json
import shutil
import subprocess
import uuid
from concurrent.futures import ThreadPoolExecutor
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any

from forestfix.agents.providers import SubprocessAgentProvider
from forestfix.domain.candidate import CandidateRecord
from forestfix.domain.task_spec import TaskSpec
from forestfix.sandbox.branches import AppliedBranch, GitApplicator
from forestfix.sandbox.container import ContainerConfig, DockerCommandExecutor
from forestfix.sandbox.executor import CommandExecutor, CommandRunner
from forestfix.sandbox.worktrees import GitWorktreeManager
from forestfix.storage.sqlite_store import SQLiteStore
from forestfix.verification.pipeline import VerificationPipeline
from forestfix.verification.reports import BaselineReport, VerificationReport


class ExecutorFactory:
    """Choose the least-privilege executor available for a task."""

    def __init__(
        self,
        *,
        allow_unsafe_local: bool,
        default_container_image: str = "python:3.12-slim",
    ) -> None:
        self.allow_unsafe_local = allow_unsafe_local
        self.default_container_image = default_container_image

    def build(
        self,
        spec: TaskSpec,
        *,
        execution_mode: str,
        container_image: str | None = None,
    ) -> CommandRunner:
        executables = {
            command[0]
            for command in (*spec.acceptance_commands, spec.reproduction_command)
        }
        image = container_image or self.default_container_image

        if execution_mode == "local":
            if not self.allow_unsafe_local:
                raise RuntimeError("local execution is disabled by the server")
            return CommandExecutor(executables, allow_unsafe_local=True)

        if execution_mode == "docker":
            return DockerCommandExecutor(
                ContainerConfig(image=image, network_access=spec.network_access)
            )

        if self.allow_unsafe_local:
            return CommandExecutor(executables, allow_unsafe_local=True)
        if shutil.which("docker"):
            return DockerCommandExecutor(
                ContainerConfig(image=image, network_access=spec.network_access)
            )
        raise RuntimeError("no secure executor is available and local execution is disabled")


class ForestFixService:
    def __init__(
        self,
        store: SQLiteStore,
        *,
        worktree_root: Path,
        allow_unsafe_local: bool,
        default_container_image: str = "python:3.12-slim",
        max_context_chars: int = 120_000,
        provider_timeout_seconds: int = 600,
    ) -> None:
        self.store = store
        self.worktree_root = worktree_root.resolve()
        self.executor_factory = ExecutorFactory(
            allow_unsafe_local=allow_unsafe_local,
            default_container_image=default_container_image,
        )
        self.max_context_chars = max_context_chars
        self.provider_timeout_seconds = provider_timeout_seconds

    def reproduce_baseline(self, spec: TaskSpec, *, execution_mode: str = "auto") -> BaselineReport:
        executor = self.executor_factory.build(spec, execution_mode=execution_mode)
        pipeline = VerificationPipeline(spec, executor, self.worktree_root)
        report = pipeline.reproduce_baseline()
        self.store.save_baseline(spec.task_id, report.model_dump(mode="json"))
        return report

    def collect_context(self, spec: TaskSpec, baseline: BaselineReport | None = None) -> str:
        tracked = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", "-z", spec.base_commit],
            cwd=spec.repo_path.resolve(),
            check=True,
            capture_output=True,
            timeout=30,
        )
        paths = [
            path
            for path in tracked.stdout.decode("utf-8", errors="replace").split("\x00")
            if path
        ]
        allowed = sorted(
            path
            for path in paths
            if any(fnmatchcase(path, pattern) for pattern in spec.allowed_paths)
        )
        chunks: list[str] = []
        total = 0
        for path in allowed:
            content = subprocess.run(
                ["git", "show", f"{spec.base_commit}:{path}"],
                cwd=spec.repo_path.resolve(),
                check=True,
                capture_output=True,
                timeout=30,
            ).stdout.decode("utf-8", errors="replace")
            block = f"### FILE: {path}\n{content}\n"
            if total + len(block) > self.max_context_chars:
                chunks.append("### Context truncated at configured limit")
                break
            chunks.append(block)
            total += len(block)

        baseline_block = ""
        if baseline is not None:
            evidence = baseline.command
            baseline_block = (
                "\n### BASELINE REPRODUCTION\n"
                f"reproduced={baseline.reproduced}\n"
                f"exit_code={evidence.exit_code}\n"
                f"stdout:\n{evidence.stdout[-8000:]}\n"
                f"stderr:\n{evidence.stderr[-8000:]}\n"
            )
        return baseline_block + "".join(chunks)

    def generate_candidates(
        self,
        spec: TaskSpec,
        providers: tuple[str, ...],
        *,
        execution_mode: str = "auto",
        container_image: str | None = None,
    ) -> tuple[CandidateRecord, ...]:
        if not providers:
            raise ValueError("at least one provider is required")
        if len(providers) > spec.candidate_count:
            raise ValueError("provider count exceeds the TaskSpec candidate budget")

        baseline = self.reproduce_baseline(spec, execution_mode=execution_mode)
        if not baseline.reproduced:
            raise RuntimeError("baseline failure could not be reproduced")
        context = self.collect_context(spec, baseline)
        executor = self.executor_factory.build(
            spec,
            execution_mode=execution_mode,
            container_image=container_image,
        )
        pipeline = VerificationPipeline(spec, executor, self.worktree_root)
        generation_root = self.worktree_root / "generation"

        def run_one(provider_name: str) -> CandidateRecord:
            candidate_id = f"{spec.task_id}-{provider_name}-{uuid.uuid4().hex[:8]}"
            self.store.create_candidate(
                candidate_id=candidate_id,
                task_id=spec.task_id,
                provider=provider_name,
                summary="",
                patch="",
                status="pending",
            )
            provider = SubprocessAgentProvider.preset(
                provider_name,
                timeout_seconds=self.provider_timeout_seconds,
                max_context_chars=self.max_context_chars,
            )
            try:
                manager = GitWorktreeManager(spec.repo_path, generation_root)
                workspace_id = f"gen-{candidate_id}"
                with manager.candidate(workspace_id, spec.base_commit) as workspace:
                    draft = provider.generate(spec, context, workspace)
                self.store.update_candidate(
                    candidate_id,
                    status="generated",
                    summary=draft.summary,
                    patch=draft.patch,
                )
                self.store.update_candidate(candidate_id, status="verifying")
                report = pipeline.verify_candidate(candidate_id, draft.patch)
                status = "accepted" if report.accepted else "rejected"
                self.store.update_candidate(
                    candidate_id,
                    status=status,
                    report=report.model_dump(mode="json"),
                )
            except Exception as error:
                self.store.update_candidate(
                    candidate_id,
                    status="error",
                    report={
                        "accepted": False,
                        "stage": "provider_error",
                        "error": str(error),
                    },
                )
            record = self.store.get_candidate(candidate_id)
            if record is None:
                raise RuntimeError(f"candidate record disappeared: {candidate_id}")
            return CandidateRecord.model_validate(record)

        with ThreadPoolExecutor(max_workers=len(providers)) as pool:
            futures = [pool.submit(run_one, provider_name) for provider_name in providers]
            return tuple(future.result() for future in futures)

    def verify_candidate(
        self,
        spec: TaskSpec,
        candidate_id: str,
        patch: str,
        *,
        execution_mode: str = "auto",
        container_image: str | None = None,
    ) -> VerificationReport:
        executor = self.executor_factory.build(
            spec,
            execution_mode=execution_mode,
            container_image=container_image,
        )
        pipeline = VerificationPipeline(spec, executor, self.worktree_root)
        report = pipeline.verify_candidate(candidate_id, patch)
        self.store.update_candidate(
            candidate_id,
            status="accepted" if report.accepted else "rejected",
            report=report.model_dump(mode="json"),
            patch=patch,
        )
        return report

    def apply_candidate(self, candidate_id: str) -> AppliedBranch:
        record = self.store.get_candidate(candidate_id)
        if record is None:
            raise KeyError(f"candidate not found: {candidate_id}")
        report = record.get("report")
        if report is None or report.get("accepted") is not True:
            raise RuntimeError("only accepted candidates can be applied")
        task = self.store.get_task(record["task_id"])
        if task is None:
            raise KeyError(f"task not found: {record['task_id']}")
        spec = TaskSpec.model_validate(json.loads(task["spec_json"]))
        applicator = GitApplicator(spec.repo_path, self.worktree_root / "applied")
        result = applicator.apply(
            task_id=spec.task_id,
            candidate_id=candidate_id,
            base_commit=spec.base_commit,
            patch=record["patch"],
        )
        self.store.update_candidate(
            candidate_id,
            status="applied",
            report={
                **record["report"],
                "applied_branch": result.branch,
                "applied_path": str(result.path),
                "applied_commit": result.commit,
            },
        )
        return result

    def candidate_to_dict(self, candidate_id: str) -> dict[str, Any]:
        record = self.store.get_candidate(candidate_id)
        if record is None:
            raise KeyError(f"candidate not found: {candidate_id}")
        return CandidateRecord.model_validate(record).to_api()
