from pathlib import Path

from forestfix.api.app import create_app
from forestfix.domain.task_spec import TaskSpec


def test_api_exposes_health_and_safe_patch_inspection():
    app = create_app()
    routes = {route.path: route for route in app.routes}

    assert "/health" in routes
    assert "/inspect-patch" in routes
    assert routes["/health"].endpoint() == {"status": "ok", "service": "forestfix"}

    response = routes["/inspect-patch"].endpoint(
        {
            "patch": "--- a/parser.py\n+++ b/parser.py\n@@ -1 +1 @@\n-old\n+new\n",
            "allowed_paths": ["parser.py"],
            "denied_paths": [],
        }
    )
    assert response["accepted"] is False
    assert response["findings"][0]["code"] == "MALFORMED_PATCH"


def test_api_persists_and_reads_task_records(tmp_path: Path) -> None:
    app = create_app(store_path=tmp_path / "forestfix.db")
    routes = {route.path: route for route in app.routes}
    spec = TaskSpec(
        task_id="api-task",
        repo_path=tmp_path / "repo",
        base_commit="a" * 40,
        reproduction_command=["python3", "reproduce.py"],
        acceptance_commands=[["python3", "-m", "pytest", "-q"]],
        allowed_paths=["src/**"],
        candidate_count=1,
        timeout_seconds=30,
    )

    created = routes["/tasks"].endpoint(spec)
    loaded = routes["/tasks/{task_id}"].endpoint(spec.task_id)

    assert created == {"task_id": "api-task", "status": "created"}
    assert loaded["task_id"] == "api-task"
    assert loaded["status"] == "created"
    assert loaded["spec"]["base_commit"] == "a" * 40


def test_api_creates_offline_demo_task(tmp_path: Path) -> None:
    app = create_app(store_path=tmp_path / "forestfix.db")
    routes = {route.path: route for route in app.routes}

    created = routes["/demo-task"].endpoint()
    loaded = routes["/tasks/{task_id}"].endpoint(created["task_id"])

    assert created["status"] == "created"
    assert loaded["spec"]["reproduction_command"] == ["python3", "test_parser.py"]
    assert Path(loaded["spec"]["repo_path"]).is_dir()
    assert routes["/demo-patch"].endpoint()["patch"].startswith("diff --git")
