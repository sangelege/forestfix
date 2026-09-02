from pathlib import Path, PurePosixPath
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator


def _validate_command(value: object) -> object:
    if not isinstance(value, (list, tuple)) or not value:
        raise ValueError("command must contain at least one argument")
    return value


Command = Annotated[tuple[str, ...], BeforeValidator(_validate_command)]


class TaskSpec(BaseModel):
    """Immutable, replayable specification for one patch evaluation task."""

    model_config = ConfigDict(frozen=True)

    task_id: str = Field(min_length=1)
    repo_path: Path
    base_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    reproduction_command: Command
    acceptance_commands: tuple[Command, ...] = Field(min_length=1)
    allowed_paths: tuple[str, ...]
    denied_paths: tuple[str, ...] = ()
    candidate_count: int = Field(ge=1, le=8)
    timeout_seconds: int = Field(ge=1, le=3600)
    network_access: bool = False

    @field_validator("acceptance_commands", mode="before")
    @classmethod
    def validate_acceptance_commands(cls, commands: object) -> object:
        if not commands:
            raise ValueError("at least one acceptance command is required")
        return commands

    @field_validator("allowed_paths", "denied_paths")
    @classmethod
    def validate_repository_relative_patterns(
        cls, patterns: tuple[str, ...]
    ) -> tuple[str, ...]:
        for pattern in patterns:
            path = PurePosixPath(pattern)
            if not pattern or "\\" in pattern or path.is_absolute() or ".." in path.parts:
                raise ValueError("path patterns must be repository-relative POSIX paths")
        return patterns
