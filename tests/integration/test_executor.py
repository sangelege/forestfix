import time
from pathlib import Path

import pytest

from forestfix.sandbox.executor import CommandExecutor


def test_executor_requires_explicit_unsafe_local_opt_in(tmp_path: Path) -> None:
    executor = CommandExecutor(allowed_executables={"python3"})

    with pytest.raises(RuntimeError, match="unsafe local execution is disabled"):
        executor.run(["python3", "-c", "print('no')"], cwd=tmp_path, timeout_seconds=10)


def test_executor_runs_argument_array_without_a_shell(tmp_path: Path) -> None:
    executor = CommandExecutor(
        allowed_executables={"python3"},
        allow_unsafe_local=True,
    )

    result = executor.run(
        ["python3", "-c", "print('verified')"],
        cwd=tmp_path,
        timeout_seconds=10,
    )

    assert result.exit_code == 0
    assert result.stdout == "verified\n"
    assert result.argv == ("python3", "-c", "print('verified')")
    assert Path(result.resolved_executable).is_absolute()


def test_executor_rejects_non_allowlisted_executable(tmp_path: Path) -> None:
    executor = CommandExecutor(
        allowed_executables={"python3"},
        allow_unsafe_local=True,
    )

    with pytest.raises(PermissionError, match="not allowlisted"):
        executor.run(["bash", "-c", "touch escaped"], cwd=tmp_path, timeout_seconds=10)

    assert not (tmp_path / "escaped").exists()


def test_executor_rejects_path_that_impersonates_allowlisted_name(tmp_path: Path) -> None:
    fake_python = tmp_path / "python3"
    fake_python.write_text("#!/bin/sh\ntouch impersonated\n")
    fake_python.chmod(0o755)
    executor = CommandExecutor(
        allowed_executables={"python3"},
        allow_unsafe_local=True,
    )

    with pytest.raises(PermissionError, match="bare executable name"):
        executor.run([str(fake_python)], cwd=tmp_path, timeout_seconds=10)

    assert not (tmp_path / "impersonated").exists()


def test_executor_kills_descendants_on_timeout(tmp_path: Path) -> None:
    marker = tmp_path / "child-finished"
    child_code = (
        "import time; time.sleep(2); "
        f"open({str(marker)!r}, 'w').write('alive')"
    )
    parent_code = (
        "import subprocess, sys, time; "
        f"subprocess.Popen([sys.executable, '-c', {child_code!r}]); "
        "time.sleep(10)"
    )
    executor = CommandExecutor(
        allowed_executables={"python3"},
        allow_unsafe_local=True,
    )

    result = executor.run(["python3", "-c", parent_code], cwd=tmp_path, timeout_seconds=1)
    time.sleep(0.6)

    assert result.timed_out is True
    assert not marker.exists()
