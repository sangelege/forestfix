"""Serializable evidence models produced by verification runs."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from forestfix.sandbox.executor import CommandResult


class CommandEvidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    argv: tuple[str, ...]
    resolved_executable: str
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool

    @classmethod
    def from_result(cls, result: CommandResult) -> "CommandEvidence":
        return cls(
            argv=result.argv,
            resolved_executable=result.resolved_executable,
            exit_code=result.exit_code,
            stdout=result.stdout,
            stderr=result.stderr,
            duration_seconds=result.duration_seconds,
            timed_out=result.timed_out,
        )


class BaselineReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    base_commit: str
    reproduced: bool
    command: CommandEvidence


class VerificationReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    candidate_id: str
    patch_sha256: str
    accepted: bool
    stage: Literal["policy_rejected", "apply_failed", "verification_failed", "accepted"]
    policy_findings: tuple[dict[str, str | None], ...] = ()
    actual_paths: tuple[str, ...] = ()
    commands: tuple[CommandEvidence, ...] = ()
    apply_error: str | None = None
