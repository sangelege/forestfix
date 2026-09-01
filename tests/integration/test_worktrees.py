import subprocess
from pathlib import Path

from forestfix.sandbox.worktrees import GitWorktreeManager


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def make_repo(path: Path) -> str:
    path.mkdir()
    git(path, "init", "-b", "main")
    git(path, "config", "user.name", "ForestFix Tests")
    git(path, "config", "user.email", "forestfix@example.invalid")
    (path / "value.txt").write_text("baseline\n")
    git(path, "add", "value.txt")
    git(path, "commit", "-m", "baseline")
    return git(path, "rev-parse", "HEAD")


def test_candidate_worktree_is_created_and_removed(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    commit = make_repo(repo)
    manager = GitWorktreeManager(repo, tmp_path / "worktrees")

    with manager.candidate("candidate-1", commit) as worktree:
        assert worktree != repo
        assert (worktree / "value.txt").read_text() == "baseline\n"
        (worktree / "value.txt").write_text("candidate\n")

    assert not worktree.exists()
    assert (repo / "value.txt").read_text() == "baseline\n"
