import base64
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXCLUDED_DIRS = {
    ".forestfix",
    ".git",
    ".venv",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "build",
    "htmlcov",
    "__pycache__",
}


def run_gh(*args: str, input_text: str | None = None) -> str:
    result = subprocess.run(
        ["gh", *args],
        cwd=ROOT,
        input=input_text,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(detail)
    return result.stdout


def files_to_sync() -> list[dict[str, str]]:
    additions: list[dict[str, str]] = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file():
            continue
        relative_parts = path.relative_to(ROOT).parts
        if any(part in EXCLUDED_DIRS for part in relative_parts):
            continue
        if path.name in {".coverage", "*.pyc"} or path.suffix in {".pyc", ".pyo"}:
            continue
        relative = path.relative_to(ROOT).as_posix()
        contents = base64.b64encode(path.read_bytes()).decode("ascii")
        additions.append({"path": relative, "contents": contents})
    return additions


def main() -> None:
    head = run_gh(
        "api",
        "repos/sangelege/forestfix/git/refs/heads/main",
        "--jq",
        ".object.sha",
    ).strip()
    additions = files_to_sync()
    variables = {
        "input": {
            "branch": {
                "repositoryNameWithOwner": "sangelege/forestfix",
                "branchName": "main",
            },
            "expectedHeadOid": head,
            "message": {
                "headline": "Sync ForestFix v0.2.0 product console",
                "body": "Add provider orchestration, product console, and candidate persistence.",
            },
            "fileChanges": {"additions": additions},
        }
    }
    payload = {
        "query": (
            "mutation($input: CreateCommitOnBranchInput!) { "
            "createCommitOnBranch(input: $input) { commit { oid } } }"
        ),
        "variables": variables,
    }
    response = run_gh(
        "api",
        "graphql",
        "--input",
        "-",
        input_text=json.dumps(payload, ensure_ascii=False),
    )
    parsed = json.loads(response)
    if "errors" in parsed:
        raise RuntimeError(json.dumps(parsed["errors"], ensure_ascii=False))
    commit = parsed["data"]["createCommitOnBranch"]["commit"]["oid"]
    print(f"Synced {len(additions)} files")
    print(f"Commit: {commit}")


if __name__ == "__main__":
    main()
