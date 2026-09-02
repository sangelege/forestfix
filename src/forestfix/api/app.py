"""FastAPI application for the ForestFix product console."""

import json
import os
import shutil
import subprocess
import uuid
from dataclasses import asdict
from importlib.resources import files as resource_files
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict

from forestfix.domain.task_spec import TaskSpec
from forestfix.orchestration.service import ForestFixService
from forestfix.policy.patch_policy import inspect_patch
from forestfix.storage.sqlite_store import SQLiteStore


class PatchInspectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patch: str
    allowed_paths: tuple[str, ...] = ()
    denied_paths: tuple[str, ...] = ()


class CandidateSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    patch: str
    execution_mode: Literal["auto", "local", "docker"] = "auto"
    container_image: str | None = None


class GenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    providers: tuple[str, ...] = ("codex",)
    execution_mode: Literal["auto", "local", "docker"] = "auto"
    container_image: str | None = None


class BaselineRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    execution_mode: Literal["auto", "local", "docker"] = "auto"
    container_image: str | None = None


def create_app(
    *,
    store_path: Path | None = None,
    allow_unsafe_local: bool = False,
    default_container_image: str = "python:3.12-slim",
) -> FastAPI:
    app = FastAPI(title="ForestFix", version="0.2.0")
    database_path = store_path or Path(os.getenv("FORESTFIX_DB", ".forestfix/forestfix.db"))
    store = SQLiteStore(database_path)
    worktree_root = database_path.resolve().parent / "worktrees"
    service = ForestFixService(
        store,
        worktree_root=worktree_root,
        allow_unsafe_local=allow_unsafe_local,
        default_container_image=default_container_image,
    )

    app.state.store = store
    app.state.service = service
    app.state.allow_unsafe_local = allow_unsafe_local

    web_root = Path(__file__).parents[1] / "web"
    app.mount("/static", StaticFiles(directory=web_root / "static"), name="static")

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return (web_root / "templates" / "index.html").read_text(encoding="utf-8")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "forestfix"}

    @app.post("/inspect-patch")
    def inspect_patch_endpoint(
        request: PatchInspectionRequest | dict[str, Any],
    ) -> dict[str, Any]:
        if isinstance(request, dict):
            request = PatchInspectionRequest.model_validate(request)
        findings = inspect_patch(
            request.patch,
            allowed_patterns=request.allowed_paths,
            denied_patterns=request.denied_paths,
        )
        return {
            "accepted": not findings,
            "findings": [asdict(finding) for finding in findings],
        }

    @app.get("/providers")
    def providers() -> dict[str, Any]:
        available = {
            "hermes": shutil.which("hermes"),
            "codex": shutil.which("codex"),
            "claude": shutil.which("claude"),
        }
        return {
            "providers": [
                {
                    "name": name,
                    "available": available[name] is not None,
                    "path": available[name],
                }
                for name in ("hermes", "codex", "claude")
            ],
            "execution": {
                "docker_available": shutil.which("docker") is not None,
                "unsafe_local_enabled": allow_unsafe_local,
            },
        }

    @app.get("/demo-patch")
    def demo_patch() -> dict[str, str]:
        return {
            "patch": resource_files("forestfix.demo_data")
            .joinpath("good.patch")
            .read_text(encoding="utf-8")
        }

    @app.post("/demo-task", status_code=201)
    def create_demo_task() -> dict[str, Any]:
        task_id = f"parser-demo-{uuid.uuid4().hex[:8]}"
        demo_root = database_path.resolve().parent / "demo-repos" / task_id
        repo = demo_root / "repo"
        repo.mkdir(parents=True)
        for name in ("parser.py", "test_parser.py"):
            (repo / name).write_text(
                resource_files("forestfix.demo_data").joinpath(name).read_text(encoding="utf-8"),
                encoding="utf-8",
            )

        def git(*args: str) -> str:
            result = subprocess.run(
                ["git", *args],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            return result.stdout.strip()

        git("init", "-b", "main")
        git("config", "user.name", "ForestFix Demo")
        git("config", "user.email", "forestfix@example.invalid")
        git("add", ".")
        git("commit", "-m", "baseline")
        commit = git("rev-parse", "HEAD")
        spec = TaskSpec(
            task_id=task_id,
            repo_path=repo,
            base_commit=commit,
            reproduction_command=["python3", "test_parser.py"],
            acceptance_commands=[["python3", "test_parser.py"]],
            allowed_paths=["parser.py", "test_parser.py"],
            candidate_count=3,
            timeout_seconds=30,
        )
        store.create_task(spec)
        return {
            "task_id": task_id,
            "status": "created",
            "spec": spec.model_dump(mode="json"),
        }

    @app.post("/tasks", status_code=201)
    def create_task(spec: TaskSpec) -> dict[str, str]:
        try:
            store.create_task(spec)
        except Exception as error:
            if "UNIQUE constraint failed" in str(error):
                raise HTTPException(status_code=409, detail="task already exists") from error
            raise
        return {"task_id": spec.task_id, "status": "created"}

    @app.get("/task-list")
    def list_tasks() -> dict[str, Any]:
        tasks = []
        for record in store.list_tasks():
            tasks.append(
                {
                    "task_id": record["task_id"],
                    "status": record["status"],
                    "spec": json.loads(record["spec_json"]),
                    "created_at": record["created_at"],
                    "updated_at": record["updated_at"],
                }
            )
        return {"tasks": tasks}

    @app.get("/tasks/{task_id}")
    def get_task(task_id: str) -> dict[str, Any]:
        record = store.get_task(task_id)
        if record is None:
            raise HTTPException(status_code=404, detail="task not found")
        result: dict[str, Any] = {
            "task_id": record["task_id"],
            "status": record["status"],
            "spec": json.loads(record["spec_json"]),
            "created_at": record["created_at"],
            "updated_at": record["updated_at"],
            "candidates": store.list_candidates(task_id),
        }
        if record["baseline_json"] is not None:
            result["baseline"] = json.loads(record["baseline_json"])
        if record["report_json"] is not None:
            result["report"] = json.loads(record["report_json"])
        return result

    @app.post("/tasks/{task_id}/baseline")
    def run_baseline(task_id: str, request: BaselineRequest | None = None) -> dict[str, Any]:
        spec = _load_task_spec(store, task_id)
        payload = request or BaselineRequest()
        report = service.reproduce_baseline(
            spec,
            execution_mode=payload.execution_mode,
        )
        store.update_task_status(task_id, "baseline_ready" if report.reproduced else "failed")
        return report.model_dump(mode="json")

    @app.post("/tasks/{task_id}/generate")
    def generate(task_id: str, request: GenerateRequest) -> dict[str, Any]:
        spec = _load_task_spec(store, task_id)
        store.update_task_status(task_id, "generating")
        candidates = service.generate_candidates(
            spec,
            request.providers,
            execution_mode=request.execution_mode,
            container_image=request.container_image,
        )
        accepted = [candidate for candidate in candidates if candidate.status == "accepted"]
        store.update_task_status(task_id, "ready" if accepted else "failed")
        return {"candidates": [candidate.to_api() for candidate in candidates]}

    @app.post("/tasks/{task_id}/verify")
    def verify_task(task_id: str, submission: CandidateSubmission) -> dict[str, Any]:
        spec = _load_task_spec(store, task_id)
        if store.get_candidate(submission.candidate_id) is None:
            store.create_candidate(
                candidate_id=submission.candidate_id,
                task_id=task_id,
                provider="manual",
                summary="",
                patch=submission.patch,
                status="pending",
            )
        report = service.verify_candidate(
            spec,
            submission.candidate_id,
            submission.patch,
            execution_mode=submission.execution_mode,
            container_image=submission.container_image,
        )
        store.update_task_status(task_id, "ready" if report.accepted else "failed")
        return report.model_dump(mode="json")

    @app.get("/tasks/{task_id}/candidates")
    def list_candidates(task_id: str) -> dict[str, Any]:
        _require_task(store, task_id)
        return {"candidates": store.list_candidates(task_id)}

    @app.get("/candidates/{candidate_id}")
    def get_candidate(candidate_id: str) -> dict[str, Any]:
        record = store.get_candidate(candidate_id)
        if record is None:
            raise HTTPException(status_code=404, detail="candidate not found")
        return record

    @app.get("/candidates/{candidate_id}/diff")
    def get_candidate_diff(candidate_id: str) -> dict[str, str]:
        record = store.get_candidate(candidate_id)
        if record is None:
            raise HTTPException(status_code=404, detail="candidate not found")
        return {"candidate_id": candidate_id, "patch": record["patch"]}

    @app.post("/candidates/{candidate_id}/apply")
    def apply_candidate(candidate_id: str) -> dict[str, str]:
        result = service.apply_candidate(candidate_id)
        return {
            "branch": result.branch,
            "path": str(result.path),
            "commit": result.commit,
        }

    return app


def _load_task_spec(store: SQLiteStore, task_id: str) -> TaskSpec:
    record = store.get_task(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="task not found")
    return TaskSpec.model_validate(json.loads(record["spec_json"]))


def _require_task(store: SQLiteStore, task_id: str) -> None:
    if store.get_task(task_id) is None:
        raise HTTPException(status_code=404, detail="task not found")


app = create_app(
    allow_unsafe_local=os.getenv("FORESTFIX_ALLOW_UNSAFE_LOCAL") == "1"
)
