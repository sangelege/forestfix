import os
import shutil
import signal
import subprocess
import sys
import time
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class CommandRunner(Protocol):
    def run(
        self,
        argv: list[str] | tuple[str, ...],
        *,
        cwd: Path,
        timeout_seconds: int,
    ) -> "CommandResult":
        ...


@dataclass(frozen=True)
class CommandResult:
    argv: tuple[str, ...]
    resolved_executable: str
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool = False


class CommandExecutor:
    """Run allowlisted argument arrays directly, never through a shell.

    This local executor is suitable for trusted Phase 0 fixtures. Untrusted
    repositories require a container-backed executor before production use.
    """

    def __init__(
        self,
        allowed_executables: set[str],
        *,
        allow_unsafe_local: bool = False,
        trusted_path: str = "/usr/local/bin:/usr/bin:/bin",
    ) -> None:
        self.allowed_executables = frozenset(allowed_executables)
        self.allow_unsafe_local = allow_unsafe_local
        self.trusted_path = trusted_path
        self._resolved_executables: dict[str, str] = {}
        for executable in self.allowed_executables:
            if Path(executable).name != executable:
                raise ValueError("allowlisted executables must use bare names")
            resolved = self._resolve_executable(executable)
            if resolved is None:
                raise FileNotFoundError(f"allowlisted executable was not found: {executable}")
            self._resolved_executables[executable] = resolved

    def _resolve_executable(self, executable: str) -> str | None:
        """Resolve a bare executable without ever searching repository paths."""
        if os.name == "nt" and executable in {"python", "python3"}:
            return str(Path(sys.executable).resolve())
        resolved = shutil.which(executable, path=self.trusted_path)
        if resolved is None and os.name == "nt":
            resolved = shutil.which(executable)
        return resolved

    def run(
        self,
        argv: list[str] | tuple[str, ...],
        *,
        cwd: Path,
        timeout_seconds: int,
    ) -> CommandResult:
        if not self.allow_unsafe_local:
            raise RuntimeError("unsafe local execution is disabled; use a sandbox executor")
        command = tuple(argv)
        if not command:
            raise ValueError("command must contain at least one argument")
        executable = Path(command[0]).name
        if command[0] != executable:
            raise PermissionError("command must use a bare executable name")
        if executable not in self.allowed_executables:
            raise PermissionError(f"executable is not allowlisted: {executable}")
        resolved_executable = self._resolved_executables[executable]
        resolved_command = (resolved_executable, *command[1:])

        started = time.monotonic()
        process = subprocess.Popen(
            resolved_command,
            cwd=cwd.resolve(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
            env={
                "HOME": str(cwd.resolve()),
                "PATH": self.trusted_path,
                "PYTHONDONTWRITEBYTECODE": "1",
            },
        )
        timed_out = False
        try:
            stdout, stderr = process.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            self._terminate_process_tree(process)
            stdout, stderr = process.communicate()

        return CommandResult(
            argv=command,
            resolved_executable=resolved_executable,
            exit_code=124 if timed_out else process.returncode,
            stdout=stdout,
            stderr=stderr,
            duration_seconds=time.monotonic() - started,
            timed_out=timed_out,
        )

    @staticmethod
    def _terminate_process_tree(process: subprocess.Popen[str]) -> None:
        """Terminate the process and its descendants without relying on POSIX only."""
        if hasattr(os, "killpg"):
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            return
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            check=False,
            capture_output=True,
        )
