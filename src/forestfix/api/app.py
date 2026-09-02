"""Minimal FastAPI application for ForestFix inspection endpoints."""

from dataclasses import asdict
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict

from forestfix.policy.patch_policy import inspect_patch


class PatchInspectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patch: str
    allowed_paths: tuple[str, ...] = ()
    denied_paths: tuple[str, ...] = ()


def create_app() -> FastAPI:
    app = FastAPI(title="ForestFix", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "forestfix"}

    @app.post("/inspect-patch")
    def inspect_patch_endpoint(request: PatchInspectionRequest | dict[str, Any]) -> dict[str, Any]:
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

    return app


app = create_app()
