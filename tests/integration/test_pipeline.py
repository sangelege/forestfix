import shutil
import subprocess
from pathlib import Path

from forestfix.domain.task_spec import TaskSpec
from forestfix.sandbox.executor import CommandExecutor
from forestfix.verification.pipeline import VerificationPipeline

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


def make_fixture_repo(tmp_path: Path) -> tuple[Path, str]:
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
        task_id="parser-task",
        repo_path=repo,
        base_commit=commit,
        reproduction_command=["python3", "test_parser.py"],
        acceptance_commands=[["python3", "test_parser.py"]],
        allowed_paths=["parser.py", "test_parser.py"],
        candidate_count=2,
        timeout_seconds=10,
    )


def test_baseline_report_confirms_the_fixture_reproduces(tmp_path: Path) -> None:
    repo, commit = make_fixture_repo(tmp_path)
    spec = make_spec(repo, commit)
    executor = CommandExecutor({"python3"}, allow_unsafe_local=True)
    pipeline = VerificationPipeline(spec, executor, tmp_path / "worktrees")

    report = pipeline.reproduce_baseline()

    assert report.reproduced is True
    assert report.command.exit_code != 0
    assert report.base_commit == commit


def test_good_candidate_is_accepted_with_command_evidence(tmp_path: Path) -> None:
    repo, commit = make_fixture_repo(tmp_path)
    spec = make_spec(repo, commit)
    executor = CommandExecutor({"python3"}, allow_unsafe_local=True)
    pipeline = VerificationPipeline(spec, executor, tmp_path / "worktrees")
    patch = (FIXTURE_ROOT / "patches" / "good.patch").read_text()

    report = pipeline.verify_candidate("good-1", patch)

    assert report.accepted is True
    assert report.stage == "accepted"
    assert report.actual_paths == ("parser.py",)
    assert len(report.commands) == 2
    assert report.commands[0].argv == ("python3", "test_parser.py")
    assert report.commands[0].exit_code == 0
    assert report.commands[1].exit_code == 0
    expected_source = "def normalize_header(value: str) -> str:\n    return value.strip().lower()\n"
    assert (repo / "parser.py").read_text() == expected_source


def test_failing_candidate_is_rejected_with_failure_evidence(tmp_path: Path) -> None:
    repo, commit = make_fixture_repo(tmp_path)
    spec = make_spec(repo, commit)
    executor = CommandExecutor({"python3"}, allow_unsafe_local=True)
    pipeline = VerificationPipeline(spec, executor, tmp_path / "worktrees")
    patch = (FIXTURE_ROOT / "patches" / "failing.patch").read_text()

    report = pipeline.verify_candidate("bad-1", patch)

    assert report.accepted is False
    assert report.stage == "verification_failed"
    assert len(report.commands) == 1
    assert report.commands[0].exit_code != 0


def test_cheating_candidate_is_rejected_before_execution(tmp_path: Path) -> None:
    repo, commit = make_fixture_repo(tmp_path)
    spec = make_spec(repo, commit)
    executor = CommandExecutor({"python3"}, allow_unsafe_local=True)
    pipeline = VerificationPipeline(spec, executor, tmp_path / "worktrees")
    patch = (FIXTURE_ROOT / "patches" / "cheating.patch").read_text()

    report = pipeline.verify_candidate("cheat-1", patch)

    assert report.accepted is False
    assert report.stage == "policy_rejected"
    assert report.commands == ()
    assert any(finding["code"] == "TEST_CHEATING" for finding in report.policy_findings)


def test_multiple_candidates_are_evaluated_independently(tmp_path: Path) -> None:
    repo, commit = make_fixture_repo(tmp_path)
    spec = make_spec(repo, commit)
    executor = CommandExecutor({"python3"}, allow_unsafe_local=True)
    pipeline = VerificationPipeline(spec, executor, tmp_path / "worktrees")
    candidates = {
        "good-1": (FIXTURE_ROOT / "patches" / "good.patch").read_text(),
        "bad-1": (FIXTURE_ROOT / "patches" / "failing.patch").read_text(),
    }

    reports = pipeline.verify_candidates(candidates)

    assert {report.candidate_id for report in reports} == {"good-1", "bad-1"}
    assert {report.accepted for report in reports} == {True, False}
    assert not any((tmp_path / "worktrees").iterdir())


def test_candidate_must_fix_the_reproduced_failure(tmp_path: Path) -> None:
    repo, commit = make_fixture_repo(tmp_path)
    spec = TaskSpec(
        task_id="parser-task-unrelated-acceptance",
        repo_path=repo,
        base_commit=commit,
        reproduction_command=["python3", "test_parser.py"],
        acceptance_commands=[["python3", "-c", "print('unrelated check')"]],
        allowed_paths=["parser.py"],
        candidate_count=1,
        timeout_seconds=10,
    )
    executor = CommandExecutor({"python3"}, allow_unsafe_local=True)
    pipeline = VerificationPipeline(spec, executor, tmp_path / "worktrees")
    patch = (FIXTURE_ROOT / "patches" / "failing.patch").read_text()

    report = pipeline.verify_candidate("bad-reproduction", patch)

    assert report.accepted is False
    assert report.stage == "verification_failed"
    assert report.commands[0].argv == ("python3", "test_parser.py")
    assert report.commands[0].exit_code != 0
