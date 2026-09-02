import shutil
import subprocess
from pathlib import Path

from forestfix.agents.providers import CandidateDraft, SubprocessAgentProvider
from forestfix.domain.task_spec import TaskSpec
from forestfix.orchestration.service import ExecutorFactory, ForestFixService
from forestfix.sandbox.branches import GitApplicator
from forestfix.sandbox.executor import CommandExecutor
from forestfix.storage.sqlite_store import SQLiteStore

FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "parser_bug"


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def make_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    shutil.copytree(FIXTURE_ROOT, repo, ignore=shutil.ignore_patterns("patches"))
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.name", "ForestFix Tests")
    git(repo, "config", "user.email", "forestfix@example.invalid")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "baseline")
    return repo, git(repo, "rev-parse", "HEAD")


def make_spec(repo: Path, commit: str) -> TaskSpec:
    return TaskSpec(
        task_id="orchestration-task",
        repo_path=repo,
        base_commit=commit,
        reproduction_command=["python3", "test_parser.py"],
        acceptance_commands=[["python3", "test_parser.py"]],
        allowed_paths=["parser.py", "test_parser.py"],
        candidate_count=2,
        timeout_seconds=10,
    )


class FakeProvider:
    def __init__(self, **_kwargs: object) -> None:
        self.provider_name = "fake"

    def generate(self, spec: TaskSpec, context: str, workspace: Path) -> CandidateDraft:
        assert spec.task_id
        assert context
        assert workspace.exists()
        return CandidateDraft(
            patch=(FIXTURE_ROOT / "patches" / "good.patch").read_text(),
            summary="normalize headers before parsing",
            provider="fake",
        )


def test_service_generates_and_verifies_candidate(tmp_path: Path, monkeypatch) -> None:
    repo, commit = make_repo(tmp_path)
    spec = make_spec(repo, commit)
    store = SQLiteStore(tmp_path / "forestfix.db")
    store.create_task(spec)
    monkeypatch.setattr(
        SubprocessAgentProvider,
        "preset",
        classmethod(lambda cls, name, **kwargs: FakeProvider(**kwargs)),
    )
    service = ForestFixService(
        store,
        worktree_root=tmp_path / "worktrees",
        allow_unsafe_local=True,
    )

    candidates = service.generate_candidates(
        spec,
        ("fake",),
        execution_mode="local",
    )

    assert len(candidates) == 1
    assert candidates[0].status == "accepted"
    assert candidates[0].report is not None
    assert candidates[0].report["accepted"] is True
    assert len(store.list_candidates(spec.task_id)) == 1


def test_auto_executor_prefers_explicit_local_mode_when_enabled(tmp_path: Path) -> None:
    repo, commit = make_repo(tmp_path)
    spec = make_spec(repo, commit)

    executor = ExecutorFactory(allow_unsafe_local=True).build(
        spec,
        execution_mode="auto",
    )

    assert isinstance(executor, CommandExecutor)


def test_service_apply_creates_local_branch_without_touching_main(tmp_path: Path) -> None:
    repo, commit = make_repo(tmp_path)
    spec = make_spec(repo, commit)
    store = SQLiteStore(tmp_path / "forestfix.db")
    store.create_task(spec)
    candidate_id = "apply-candidate"
    patch = (FIXTURE_ROOT / "patches" / "good.patch").read_text()
    store.create_candidate(
        candidate_id=candidate_id,
        task_id=spec.task_id,
        provider="manual",
        summary="verified patch",
        patch=patch,
        status="accepted",
    )
    store.update_candidate(
        candidate_id,
        report={"accepted": True, "stage": "accepted", "patch_sha256": "x" * 64},
    )
    service = ForestFixService(
        store,
        worktree_root=tmp_path / "worktrees",
        allow_unsafe_local=True,
    )

    result = service.apply_candidate(candidate_id)

    assert result.branch == f"forestfix/{spec.task_id}/{candidate_id}"
    assert result.commit
    assert "forestfix/" in git(repo, "branch", "--list")
    assert git(repo, "status", "--porcelain") == ""


def test_git_applicator_rejects_non_patch_content(tmp_path: Path) -> None:
    repo, commit = make_repo(tmp_path)
    applicator = GitApplicator(repo, tmp_path / "applied")

    try:
        applicator.apply(
            task_id="bad-task",
            candidate_id="bad-candidate",
            base_commit=commit,
            patch="not a patch",
        )
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected git apply to fail")

    assert git(repo, "status", "--porcelain") == ""
