"""Command-line interface for the deterministic ForestFix core."""

import argparse
import json
import subprocess
import sys
import tempfile
from importlib.resources import files as resource_files
from pathlib import Path
from typing import Any

from forestfix.domain.task_spec import TaskSpec
from forestfix.sandbox.executor import CommandExecutor
from forestfix.verification.pipeline import VerificationPipeline

_FIXTURE_ROOT = Path(__file__).parents[2] / "tests" / "fixtures" / "parser_bug"


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _read_demo_file(name: str) -> str:
    development_file = _FIXTURE_ROOT / name
    if development_file.is_file():
        return development_file.read_text(encoding="utf-8")
    return resource_files("forestfix.demo_data").joinpath(name).read_text(encoding="utf-8")


def _fixture_repo(root: Path) -> tuple[Path, str]:
    repo = root / "repo"
    repo.mkdir()
    for name in ("parser.py", "test_parser.py"):
        (repo / name).write_text(_read_demo_file(name), encoding="utf-8")
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "ForestFix Demo")
    _git(repo, "config", "user.email", "forestfix@example.invalid")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "baseline")
    return repo, _git(repo, "rev-parse", "HEAD")


def _demo() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="forestfix-demo-") as directory:
        repo, commit = _fixture_repo(Path(directory))
        spec = TaskSpec(
            task_id="parser-demo",
            repo_path=repo,
            base_commit=commit,
            reproduction_command=["python3", "test_parser.py"],
            acceptance_commands=[["python3", "test_parser.py"]],
            allowed_paths=["parser.py", "test_parser.py"],
            candidate_count=2,
            timeout_seconds=10,
        )
        executor = CommandExecutor({"python3"}, allow_unsafe_local=True)
        pipeline = VerificationPipeline(spec, executor, Path(directory) / "worktrees")
        baseline = pipeline.reproduce_baseline()
        good = pipeline.verify_candidate(
            "good-demo", _read_demo_file("good.patch")
        )
        cheating = pipeline.verify_candidate(
            "cheating-demo",
            _read_demo_file("cheating.patch"),
        )
        return {
            "baseline": baseline.model_dump(mode="json"),
            "good_candidate": good.model_dump(mode="json"),
            "cheating_candidate": cheating.model_dump(mode="json"),
        }


def _load_spec(path: Path) -> TaskSpec:
    data = json.loads(path.read_text(encoding="utf-8"))
    repo_path = Path(data["repo_path"])
    if not repo_path.is_absolute():
        data["repo_path"] = str((path.parent / repo_path).resolve())
    return TaskSpec.model_validate(data)


def _verify(args: argparse.Namespace) -> int:
    spec_path = Path(args.spec).resolve()
    spec = _load_spec(spec_path)
    executables = {
        command[0]
        for command in (*spec.acceptance_commands, spec.reproduction_command)
    }
    executor = CommandExecutor(executables, allow_unsafe_local=args.unsafe_local)
    pipeline = VerificationPipeline(spec, executor, Path(args.worktree_root).resolve())
    baseline = pipeline.reproduce_baseline()
    if not baseline.reproduced:
        payload = {"baseline": baseline.model_dump(mode="json"), "verification": None}
        _write_or_print(payload, args.output)
        return 2

    patch = Path(args.patch).read_text(encoding="utf-8")
    verification = pipeline.verify_candidate(args.candidate_id, patch)
    payload = {
        "baseline": baseline.model_dump(mode="json"),
        "verification": verification.model_dump(mode="json"),
    }
    _write_or_print(payload, args.output)
    return 0 if verification.accepted else 1


def _write_or_print(payload: dict[str, Any], output: str | None) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if output:
        Path(output).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)


def _run_demo_command(_args: argparse.Namespace) -> int:
    print(json.dumps(_demo(), ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="forestfix")
    subparsers = parser.add_subparsers(dest="command", required=True)

    demo = subparsers.add_parser("demo", help="run the offline parser fixture demo")
    demo.set_defaults(handler=_run_demo_command)

    verify = subparsers.add_parser("verify", help="verify one candidate patch")
    verify.add_argument("--spec", required=True, help="TaskSpec JSON file")
    verify.add_argument("--patch", required=True, help="candidate patch file")
    verify.add_argument("--candidate-id", required=True)
    verify.add_argument("--worktree-root", default=".forestfix-worktrees")
    verify.add_argument("--output", help="write JSON report to this path")
    verify.add_argument(
        "--unsafe-local",
        action="store_true",
        help="explicitly allow trusted-fixture local execution; not a security sandbox",
    )
    verify.set_defaults(handler=_verify)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.handler(args))
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        print(f"forestfix: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
