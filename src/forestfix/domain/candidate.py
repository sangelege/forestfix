"""Candidate records exchanged between orchestration, storage, and the API."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class CandidateRecord(BaseModel):
    """A frozen candidate plus its persisted lifecycle state."""

    model_config = ConfigDict(frozen=True)

    candidate_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    summary: str = ""
    patch: str = ""
    report: dict[str, Any] | None = None
    status: Literal[
        "pending",
        "generated",
        "verifying",
        "accepted",
        "rejected",
        "error",
        "applied",
    ] = "pending"

    def to_api(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "task_id": self.task_id,
            "provider": self.provider,
            "summary": self.summary,
            "patch": self.patch,
            "report": self.report,
            "status": self.status,
        }
