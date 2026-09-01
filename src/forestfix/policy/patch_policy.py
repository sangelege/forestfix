from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import PurePosixPath


@dataclass(frozen=True)
class PolicyFinding:
    code: str
    message: str
    path: str | None = None


def inspect_patch(
    patch: str,
    *,
    allowed_patterns: tuple[str, ...],
    denied_patterns: tuple[str, ...],
) -> tuple[PolicyFinding, ...]:
    """Inspect a unified Git patch without applying it."""
    findings: list[PolicyFinding] = []
    changed_paths = {
        line.split(" b/", maxsplit=1)[1]
        for line in patch.splitlines()
        if line.startswith("diff --git a/") and " b/" in line
    }
    if not changed_paths:
        return (
            PolicyFinding("MALFORMED_PATCH", "patch contains no parseable Git file headers"),
        )
    for path in sorted(changed_paths):
        if any(fnmatchcase(path, pattern) for pattern in denied_patterns):
            findings.append(
                PolicyFinding("DENIED_PATH", "patch changes an explicitly denied path", path)
            )
        elif not any(fnmatchcase(path, pattern) for pattern in allowed_patterns):
            findings.append(
                PolicyFinding("OUTSIDE_ALLOWED_SCOPE", "patch changes a path outside scope", path)
            )

    current_path: str | None = None
    suspicious_test_additions = (
        "@pytest.mark.skip",
        "@pytest.mark.xfail",
        "pytest.skip(",
        "@unittest.skip",
    )
    for line in patch.splitlines():
        if line.startswith("diff --git a/") and " b/" in line:
            current_path = line.split(" b/", maxsplit=1)[1]
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
