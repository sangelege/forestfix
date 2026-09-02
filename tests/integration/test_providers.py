import json
import subprocess
import sys
from pathlib import Path

from forestfix.agents.providers import SubprocessAgentProvider
from forestfix.domain.task_spec import TaskSpec


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def make_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.name", "ForestFix Tests")
    git(repo, "config", "user.email", "forestfix@example.invalid")
    (repo / "parser.py").write_text("return False\n")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "baseline")
    return repo, git(repo, "rev-parse", "HEAD")


def test_subprocess_provider_returns_structured_candidate_without_editing_repo(
    tmp_path: Path,
) -> None:
    repo, commit = make_repo(tmp_path)
    spec = TaskSpec(
        task_id="provider-task",
        repo_path=repo,
        base_commit=commit,
        reproduction_command=["python3", "reproduce.py"],
        acceptance_commands=[["python3", "-m", "pytest", "-q"]],
        allowed_paths=["parser.py"],
        candidate_count=1,
        timeout_seconds=30,
    )
    patch = "diff --git a/parser.py b/parser.py\n--- a/parser.py\n+++ b/parser.py\n"
    response = json.dumps({"patch": patch, "summary": "return true"})
    code = f"import sys; print({response!r})"
    provider = SubprocessAgentProvider(
        command=(sys.executable, "-c", code), provider_name="fake", timeout_seconds=10
    )

    candidate = provider.generate(spec, "focus on the parser", repo)

    assert candidate.patch == patch
    assert candidate.provider == "fake"
    assert candidate.summary == "return true"
    assert git(repo, "status", "--porcelain") == ""


def test_subprocess_provider_parses_markdown_fenced_json(
    tmp_path: Path,
) -> None:
    repo, commit = make_repo(tmp_path)
    spec = TaskSpec(
        task_id="provider-fenced-task",
        repo_path=repo,
        base_commit=commit,
        reproduction_command=["python3", "reproduce.py"],
        acceptance_commands=[["python3", "-m", "pytest", "-q"]],
        allowed_paths=["parser.py"],
        candidate_count=1,
        timeout_seconds=30,
    )
    patch = "diff --git a/parser.py b/parser.py\n--- a/parser.py\n+++ b/parser.py\n"
    response = json.dumps({"patch": patch, "summary": "fenced summary"})
    code = (
        "import sys; sys.stdout.write('prefix\\n```json\\n' + "
        f"{response!r} + '\\n```\\nsuffix\\n')"
    )
    provider = SubprocessAgentProvider(
        command=(sys.executable, "-c", code), provider_name="fake", timeout_seconds=10
    )

    candidate = provider.generate(spec, "context", repo)

    assert candidate.patch == patch
    assert candidate.summary == "fenced summary"
