import re
import shutil
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

_CANDIDATE_ID = re.compile(r"^[A-Za-z0-9._-]+$")


class GitWorktreeManager:
    """Create disposable detached worktrees for candidate patches."""

    def __init__(self, repository: Path, worktree_root: Path) -> None:
        self.repository = repository.resolve()
        self.worktree_root = worktree_root.resolve()

    @contextmanager
    def candidate(self, candidate_id: str, base_commit: str) -> Iterator[Path]:
        if not _CANDIDATE_ID.fullmatch(candidate_id):
            raise ValueError("candidate_id contains unsafe characters")
        self.worktree_root.mkdir(parents=True, exist_ok=True)
        target = self.worktree_root / candidate_id
        if target.exists():
            raise FileExistsError(target)

        subprocess.run(
            ["git", "worktree", "add", "--detach", str(target), base_commit],
            cwd=self.repository,
            check=True,
            capture_output=True,
            text=True,
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
            )
            if removal.returncode != 0:
                shutil.rmtree(target, ignore_errors=True)
                subprocess.run(
                    ["git", "worktree", "prune"],
                    cwd=self.repository,
                    check=False,
                    capture_output=True,
                    text=True,
                )
