import re
import shutil
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

_CANDIDATE_ID = re.compile(r"^[A-Za-z0-9._-]+$")


class GitWorktreeManager:
    """Create disposable detached worktrees for candidate patches."""

    def __init__(
        self,
        repository: Path,
        worktree_root: Path,
        *,
        git_timeout_seconds: float = 30,
    ) -> None:
        self.repository = repository.resolve()
        self.worktree_root = worktree_root.resolve()
        self.git_timeout_seconds = git_timeout_seconds

    @contextmanager
    def candidate(self, candidate_id: str, base_commit: str) -> Iterator[Path]:
        if not _CANDIDATE_ID.fullmatch(candidate_id):
            raise ValueError("candidate_id contains unsafe characters")
        self.worktree_root.mkdir(parents=True, exist_ok=True)
        target = self.worktree_root / candidate_id
        if target.exists():
            raise FileExistsError(target)

        subprocess.run(
            [
                "git",
                "-c",
                "core.hooksPath=/dev/null",
                "worktree",
                "add",
                "--detach",
                str(target),
                base_commit,
            ],
            cwd=self.repository,
            check=True,
            capture_output=True,
            text=True,
            timeout=self.git_timeout_seconds,
        )
        try:
            yield target
        finally:
            removal = subprocess.run(
                ["git", "worktree", "remove", "--force", str(target)],
                cwd=self.repository,
                check=False,
                capture_output=True,
                text=True,
                timeout=self.git_timeout_seconds,
            )
            if removal.returncode == 0:
                if target.exists():
                    raise RuntimeError("worktree cleanup failed: target directory remains")
            elif removal.returncode != 0:
                shutil.rmtree(target, ignore_errors=True)
                prune = subprocess.run(
                    ["git", "worktree", "prune"],
                    cwd=self.repository,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=self.git_timeout_seconds,
                )
                if target.exists() or prune.returncode != 0:
                    details = removal.stderr.strip() or prune.stderr.strip() or "unknown error"
                    raise RuntimeError(f"worktree cleanup failed: {details}")
