"""Docker-backed execution for untrusted repository candidates."""

import os
import shutil
import signal
import subprocess
import time
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from forestfix.sandbox.executor import CommandResult


@dataclass(frozen=True)
class ContainerConfig:
    image: str
    network_access: bool = False
    memory: str = "1g"
    cpus: str = "1.0"
    pids_limit: int = 256
    tmpfs_size: str = "64m"

    def __post_init__(self) -> None:
        if not self.image or any(char.isspace() or ord(char) < 32 for char in self.image):
            raise ValueError("container image must be a non-empty single token")
        if self.pids_limit < 1:
            raise ValueError("pids_limit must be positive")


class DockerCommandExecutor:
    """Run commands in a disposable, least-privilege Docker container."""

    def __init__(self, config: ContainerConfig) -> None:
        self.config = config
        self.docker = "docker"
        self._docker_path = shutil.which("docker") or "docker"

    def build_command(self, argv: list[str] | tuple[str, ...], cwd: Path) -> list[str]:
        command = tuple(argv)
        if not command:
            raise ValueError("command must contain at least one argument")
        network = "bridge" if self.config.network_access else "none"
        return [
            self.docker,
            "run",
            "--rm",
            "--network",
            network,
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--pids-limit",
            str(self.config.pids_limit),
            "--memory",
            self.config.memory,
            "--cpus",
            self.config.cpus,
            "--tmpfs",
            f"/tmp:rw,noexec,nosuid,size={self.config.tmpfs_size}",
            "-v",
            f"{cwd.resolve()}:/workspace:rw",
            "-w",
            "/workspace",
            self.config.image,
            *command,
        ]

    def run(
        self,
        argv: list[str] | tuple[str, ...],
        *,
        cwd: Path,
        timeout_seconds: int,
    ) -> CommandResult:
        command = tuple(argv)
        docker_command = self.build_command(command, cwd)
        started = time.monotonic()
        run_command = [self._docker_path, *docker_command[1:]]
        process = subprocess.Popen(
            run_command,
            cwd=cwd.resolve(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
            env={
                "HOME": "/root",
                "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            },
        )
        timed_out = False
        try:
            stdout, stderr = process.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate()
        return CommandResult(
            argv=command,
            resolved_executable=self.docker,
            exit_code=124 if timed_out else process.returncode,
            stdout=stdout,
            stderr=stderr,
            duration_seconds=time.monotonic() - started,
            timed_out=timed_out,
        )
