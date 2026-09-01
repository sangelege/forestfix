from pathlib import Path

import pytest

from forestfix.sandbox.executor import CommandExecutor


def test_executor_runs_argument_array_without_a_shell(tmp_path: Path) -> None:
    executor = CommandExecutor(allowed_executables={"python3"})

    result = executor.run(
        ["python3", "-c", "print('verified')"],
        cwd=tmp_path,
        timeout_seconds=10,
    )

    assert result.exit_code == 0
    assert result.stdout == "verified\n"
    assert result.argv == ("python3", "-c", "print('verified')")


def test_executor_rejects_non_allowlisted_executable(tmp_path: Path) -> None:
    executor = CommandExecutor(allowed_executables={"python3"})

    with pytest.raises(PermissionError, match="not allowlisted"):
        executor.run(["bash", "-c", "touch escaped"], cwd=tmp_path, timeout_seconds=10)

    assert not (tmp_path / "escaped").exists()


def test_executor_rejects_path_that_impersonates_allowlisted_name(tmp_path: Path) -> None:
    fake_python = tmp_path / "python3"
    fake_python.write_text("#!/bin/sh\ntouch impersonated\n")
    fake_python.chmod(0o755)
    executor = CommandExecutor(allowed_executables={"python3"})

    with pytest.raises(PermissionError, match="bare executable name"):
        executor.run([str(fake_python)], cwd=tmp_path, timeout_seconds=10)

    assert not (tmp_path / "impersonated").exists()
