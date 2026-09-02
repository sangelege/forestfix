import json
from pathlib import Path

from forestfix.domain.task_spec import TaskSpec
from forestfix.storage.sqlite_store import SQLiteStore


def make_spec(tmp_path: Path) -> TaskSpec:
    return TaskSpec(
        task_id="persisted-task",
        repo_path=tmp_path / "repo",
        base_commit="a" * 40,
        reproduction_command=["python3", "reproduce.py"],
        acceptance_commands=[["python3", "-m", "pytest", "-q"]],
        allowed_paths=["src/**"],
        candidate_count=2,
        timeout_seconds=60,
    )


def test_task_store_round_trips_spec_and_report(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "forestfix.db")
    spec = make_spec(tmp_path)
    report = {"accepted": True, "candidate_id": "candidate-1"}

    store.create_task(spec)
    store.save_report(spec.task_id, report)

    task = store.get_task(spec.task_id)
    assert task is not None
    assert task["task_id"] == spec.task_id
    assert task["status"] == "completed"
    assert json.loads(task["spec_json"])["base_commit"] == "a" * 40
    assert json.loads(task["report_json"]) == report
