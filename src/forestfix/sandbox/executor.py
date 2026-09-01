import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CommandResult:
    argv: tuple[str, ...]
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float


class CommandExecutor:
    """Run allowlisted argument arrays directly, never through a shell.

    This local executor is suitable for trusted Phase 0 fixtures. Untrusted
    repositories require a container-backed executor before production use.
    """

    def __init__(self, allowed_executables: set[str]) -> None:
        self.allowed_executables = frozenset(allowed_executables)

    def run(
        self,
        argv: list[str] | tuple[str, ...],
        *,
        cwd: Path,
        timeout_seconds: int,
    ) -> CommandResult:
        command = tuple(argv)
        if not command:
            raise ValueError("command must contain at least one argument")
        executable = Path(command[0]).name
        if command[0] != executable:
            raise PermissionError("command must use a bare executable name")
        if executable not in self.allowed_executables:
            raise PermissionError(f"executable is not allowlisted: {executable}")

        started = time.monotonic()
        completed = subprocess.run(
            command,
            cwd=cwd.resolve(),
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env={
                "HOME": str(cwd.resolve()),
                "PATH": os.environ.get("PATH", ""),
                "PYTHONDONTWRITEBYTECODE": "1",
            },
        )
        return CommandResult(
            argv=command,
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            duration_seconds=time.monotonic() - started,
        )
