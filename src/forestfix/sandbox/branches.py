"""Safe local branch application for accepted candidates."""

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

_SAFE_BRANCH_COMPONENT = re.compile(r"^[A-Za-z0-9._-]+$")


@dataclass(frozen=True)
class AppliedBranch:
    branch: str
    path: Path
    commit: str


class GitApplicator:
    """Apply an approved patch to a new local branch without touching main."""

    def __init__(
        self,
        repository: Path,
        worktree_root: Path,
        git_timeout_seconds: float = 30,
    ) -> None:
        self.repository = repository.resolve()
        self.worktree_root = worktree_root.resolve()
        self.git_timeout_seconds = git_timeout_seconds

    def apply(
        self,
        *,
        task_id: str,
        candidate_id: str,
        base_commit: str,
        patch: str,
    ) -> AppliedBranch:
        if not _SAFE_BRANCH_COMPONENT.fullmatch(task_id):
            raise ValueError("task_id contains unsafe characters")
        if not _SAFE_BRANCH_COMPONENT.fullmatch(candidate_id):
            raise ValueError("candidate_id contains unsafe characters")
        branch = f"forestfix/{task_id}/{candidate_id}"
        self.worktree_root.mkdir(parents=True, exist_ok=True)
        target = self.worktree_root / candidate_id
        if target.exists():
            raise FileExistsError(target)

        try:
            subprocess.run(
                [
                    "git",
                    "-c",
                    "core.hooksPath=/dev/null",
                    "-c",
                    "core.autocrlf=false",
                    "worktree",
                    "add",
                    "-b",
                    branch,
                    str(target),
                    base_commit,
                ],
                cwd=self.repository,
                check=True,
                capture_output=True,
                text=True,
                timeout=self.git_timeout_seconds,
            )
            applied = subprocess.run(
                [
                    "git",
                    "-c",
                    "core.hooksPath=/dev/null",
                    "-c",
                    "core.autocrlf=false",
                    "apply",
                    "--whitespace=error",
                    "-",
                ],
                cwd=target,
                input=patch.encode("utf-8"),
                check=False,
                capture_output=True,
                timeout=self.git_timeout_seconds,
            )
            if applied.returncode != 0:
                detail = applied.stderr.decode("utf-8", errors="replace").strip()
                raise RuntimeError(detail or "git apply failed")

            subprocess.run(
                ["git", "add", "-A"],
                cwd=target,
                check=True,
                capture_output=True,
                text=True,
                timeout=self.git_timeout_seconds,
            )
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=ForestFix",
                    "-c",
                    "user.email=forestfix@example.invalid",
                    "commit",
                    "-m",
                    f"Apply verified candidate {candidate_id}",
                ],
                cwd=target,
                check=True,
                capture_output=True,
                text=True,
                timeout=self.git_timeout_seconds,
            )
            commit = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=target,
                check=True,
                capture_output=True,
                text=True,
                timeout=self.git_timeout_seconds,
            ).stdout.strip()
        except Exception:
            self._discard(target, branch)
            raise

        return AppliedBranch(branch=branch, path=target, commit=commit)

    def _discard(self, target: Path, branch: str) -> None:
        removal = subprocess.run(
            ["git", "worktree", "remove", "--force", str(target)],
            cwd=self.repository,
            check=False,
            capture_output=True,
            text=True,
            timeout=self.git_timeout_seconds,
        )
        if removal.returncode != 0:
            self._remove_tree(target)
        subprocess.run(
            ["git", "branch", "-D", branch],
            cwd=self.repository,
            check=False,
            capture_output=True,
            text=True,
            timeout=self.git_timeout_seconds,
        )

    @staticmethod
    def _remove_tree(target: Path) -> None:
        if not target.exists():
            return

        def make_writable(_function: object, path: str, _error: object) -> None:
            Path(path).chmod(0o700)

        shutil.rmtree(target, onexc=make_writable)
