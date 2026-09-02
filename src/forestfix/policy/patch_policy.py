import shlex
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import PurePosixPath


@dataclass(frozen=True)
class PolicyFinding:
    code: str
    message: str
    path: str | None = None


def _safe_repo_path(path: str) -> str:
    candidate = PurePosixPath(path)
    if (
        not path
        or "\x00" in path
        or "\\" in path
        or candidate.is_absolute()
        or ".." in candidate.parts
    ):
        raise ValueError("unsafe repository path")
    return path


def _parse_one_path(raw: str) -> str:
    parts = shlex.split(raw, posix=True)
    if len(parts) != 1:
        raise ValueError("unsupported quoted path")
    return _safe_repo_path(parts[0])


def _parse_diff_header(line: str) -> tuple[str, str]:
    parts = shlex.split(line, posix=True)
    if len(parts) != 4 or parts[:2] != ["diff", "--git"]:
        raise ValueError("malformed Git diff header")
    old_token, new_token = parts[2:]
    if not old_token.startswith("a/") or not new_token.startswith("b/"):
        raise ValueError("Git diff paths must use a/ and b/ prefixes")
    return _safe_repo_path(old_token[2:]), _safe_repo_path(new_token[2:])


def _parse_changed_paths(patch: str) -> tuple[set[str], dict[int, str]]:
    paths: set[str] = set()
    destinations: dict[int, str] = {}
    has_section = False
    in_section = False

    for index, line in enumerate(patch.splitlines()):
        if line.startswith("diff --git"):
            old_path, new_path = _parse_diff_header(line)
            paths.update((old_path, new_path))
            destinations[index] = new_path
            has_section = True
            in_section = True
        elif line.startswith("rename from "):
            if not in_section:
                raise ValueError("rename metadata outside a diff section")
            paths.add(_parse_one_path(line.removeprefix("rename from ")))
        elif line.startswith("rename to "):
            if not in_section:
                raise ValueError("rename metadata outside a diff section")
            paths.add(_parse_one_path(line.removeprefix("rename to ")))
        elif line.startswith(("--- ", "+++ ")) and not in_section:
            raise ValueError("file header outside a Git diff section")

    if not has_section:
        raise ValueError("patch contains no Git diff sections")
    return paths, destinations


def inspect_paths(
    paths: set[str] | tuple[str, ...],
    *,
    allowed_patterns: tuple[str, ...],
    denied_patterns: tuple[str, ...],
) -> tuple[PolicyFinding, ...]:
    """Apply deterministic allow/deny rules to repository-relative paths."""
    findings: list[PolicyFinding] = []
    try:
        safe_paths = {_safe_repo_path(path) for path in paths}
    except ValueError:
        return (PolicyFinding("UNSAFE_PATH", "change contains an unsafe repository path"),)

    for path in sorted(safe_paths):
        if any(fnmatchcase(path, pattern) for pattern in denied_patterns):
            findings.append(
                PolicyFinding("DENIED_PATH", "patch changes an explicitly denied path", path)
            )
        elif not any(fnmatchcase(path, pattern) for pattern in allowed_patterns):
            findings.append(
                PolicyFinding("OUTSIDE_ALLOWED_SCOPE", "patch changes a path outside scope", path)
            )
    return tuple(findings)


def inspect_patch(
    patch: str,
    *,
    allowed_patterns: tuple[str, ...],
    denied_patterns: tuple[str, ...],
) -> tuple[PolicyFinding, ...]:
    """Fail-closed preliminary inspection of a unified Git patch."""
    try:
        changed_paths, destinations = _parse_changed_paths(patch)
    except (ValueError, UnicodeError) as error:
        return (PolicyFinding("MALFORMED_PATCH", str(error)),)

    findings = list(
        inspect_paths(
            changed_paths,
            allowed_patterns=allowed_patterns,
            denied_patterns=denied_patterns,
        )
    )

    current_path: str | None = None
    suspicious_test_additions = (
        "@pytest.mark.skip",
        "@pytest.mark.xfail",
        "pytest.skip(",
        "pytestmark",
        "@unittest.skip",
        "@unittest.skipIf",
        "@unittest.skipUnless",
    )
    for index, line in enumerate(patch.splitlines()):
        if index in destinations:
            current_path = destinations[index]
            continue
        filename = PurePosixPath(current_path).name if current_path is not None else ""
        is_test_path = current_path is not None and (
            current_path.startswith("tests/")
            or filename.startswith("test_")
            or filename.endswith("_test.py")
        )
        if (
            is_test_path
            and line.startswith("+")
            and not line.startswith("+++")
            and any(marker in line for marker in suspicious_test_additions)
        ):
            findings.append(
                PolicyFinding(
                    "TEST_CHEATING",
                    "patch adds a test skip or expected failure",
                    current_path,
                )
            )
            break
    return tuple(findings)
