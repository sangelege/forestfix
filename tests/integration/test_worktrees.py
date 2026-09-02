import subprocess
from pathlib import Path

import pytest

from forestfix.sandbox import worktrees as worktrees_module
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


def test_candidate_creation_disables_repository_hooks(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    commit = make_repo(repo)
    marker = tmp_path / "hook-ran"
    hook = repo / ".git" / "hooks" / "post-checkout"
    hook.write_text(f"#!/bin/sh\ntouch {marker}\n")
    hook.chmod(0o755)
    manager = GitWorktreeManager(repo, tmp_path / "worktrees")

    with manager.candidate("candidate-1", commit):
        pass

    assert not marker.exists()


def test_all_git_operations_have_timeouts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    commit = make_repo(repo)
    observed_timeouts: list[float | None] = []
    original_run = subprocess.run

    def tracked_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        observed_timeouts.append(kwargs.get("timeout"))  # type: ignore[arg-type]
        return original_run(*args, **kwargs)  # type: ignore[call-overload]

    monkeypatch.setattr(worktrees_module.subprocess, "run", tracked_run)
    manager = GitWorktreeManager(repo, tmp_path / "worktrees", git_timeout_seconds=5)

    with manager.candidate("candidate-1", commit):
        pass

    assert observed_timeouts
    assert set(observed_timeouts) == {5}


def test_cleanup_failure_is_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    commit = make_repo(repo)
    manager = GitWorktreeManager(repo, tmp_path / "worktrees")
    original_run = subprocess.run

    def fail_cleanup(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        command = args[0]
        if isinstance(command, list) and ("remove" in command or "prune" in command):
            return subprocess.CompletedProcess(command, 1, "", "simulated cleanup failure")
        return original_run(*args, **kwargs)  # type: ignore[call-overload]

    with (
        pytest.raises(RuntimeError, match="cleanup failed"),
        manager.candidate("candidate-1", commit),
    ):
        monkeypatch.setattr(worktrees_module.subprocess, "run", fail_cleanup)


def test_successful_git_cleanup_must_remove_the_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    commit = make_repo(repo)
    manager = GitWorktreeManager(repo, tmp_path / "worktrees")
    original_run = subprocess.run

    def fake_success(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        command = args[0]
        if isinstance(command, list) and "remove" in command:
            return subprocess.CompletedProcess(command, 0, "", "")
        return original_run(*args, **kwargs)  # type: ignore[call-overload]

    with (
        pytest.raises(RuntimeError, match="cleanup failed"),
        manager.candidate("candidate-1", commit),
    ):
        monkeypatch.setattr(worktrees_module.subprocess, "run", fake_success)
