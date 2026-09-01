from pathlib import Path

import pytest
from pydantic import ValidationError

from forestfix.domain.task_spec import TaskSpec


def valid_spec_data(tmp_path: Path) -> dict:
    return {
        "task_id": "task-001",
        "repo_path": str(tmp_path / "repo"),
        "base_commit": "a" * 40,
        "reproduction_command": ["pytest", "tests/test_parser.py", "-q"],
        "acceptance_commands": [["pytest", "-q"], ["ruff", "check", "."]],
        "allowed_paths": ["src/parser/**", "tests/test_parser.py"],
        "denied_paths": ["pyproject.toml", ".github/**"],
        "candidate_count": 2,
        "timeout_seconds": 300,
        "network_access": False,
    }


def test_task_spec_accepts_a_complete_safe_task(tmp_path: Path) -> None:
    spec = TaskSpec.model_validate(valid_spec_data(tmp_path))

    assert spec.task_id == "task-001"
    assert spec.reproduction_command == ("pytest", "tests/test_parser.py", "-q")
    assert spec.acceptance_commands[1] == ("ruff", "check", ".")
    assert spec.base_commit == "a" * 40


def test_task_spec_rejects_paths_that_escape_the_repository(tmp_path: Path) -> None:
    data = valid_spec_data(tmp_path)
    data["allowed_paths"] = ["../secrets/**"]

    with pytest.raises(ValidationError, match="repository-relative"):
        TaskSpec.model_validate(data)


def test_task_spec_rejects_empty_commands(tmp_path: Path) -> None:
    data = valid_spec_data(tmp_path)
    data["reproduction_command"] = []

    with pytest.raises(ValidationError, match="at least one argument"):
        TaskSpec.model_validate(data)
