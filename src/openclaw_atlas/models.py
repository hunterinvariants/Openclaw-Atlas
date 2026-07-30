from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


SCHEMA_VERSION = "1.0"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FaultKind(str, Enum):
    timeout = "timeout"
    malformed_response = "malformed_response"
    stale_data = "stale_data"
    permission_denied = "permission_denied"


class WorkflowStep(StrictModel):
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    response: Any = None
    mutating: bool = False


class FaultSpec(StrictModel):
    step: int = Field(ge=0)
    kind: FaultKind
    attempts: int = Field(default=1, ge=1)


class TaskSpec(StrictModel):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    id: str
    title: str
    prompt: str
    workflow: list[WorkflowStep]
    expected_answer_contains: list[str]
    max_tool_calls: int = Field(ge=0)
    retry_limit: int = Field(default=1, ge=0, le=5)
    fault: FaultSpec | None = None
    tags: list[str] = Field(default_factory=list)


class TraceEvent(StrictModel):
    sequence: int
    kind: Literal["tool_call", "tool_result", "final"]
    tool: str | None = None
    arguments: dict[str, Any] | None = None
    result: Any = None
    error: str | None = None
    attempt: int = 1


class Trace(StrictModel):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    task_id: str
    events: list[TraceEvent]
    final_answer: str
    status: Literal["completed", "failed", "blocked"]

    def canonical_payload(self) -> str:
        return json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))

    @property
    def digest(self) -> str:
        return sha256(self.canonical_payload().encode()).hexdigest()


class DimensionScore(StrictModel):
    value: float = Field(ge=0, le=1)
    reason: str


class EvaluationResult(StrictModel):
    task_id: str
    trace_digest: str
    scores: dict[str, DimensionScore]
    overall: float = Field(ge=0, le=1)
    passed: bool


class EvaluationReport(StrictModel):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    generated_at: str
    dataset: str
    task_count: int
    pass_count: int
    overall: float
    dimensions: dict[str, float]
    results: list[EvaluationResult]

    @classmethod
    def create(cls, dataset: str, results: list[EvaluationResult]) -> "EvaluationReport":
        dimensions = {
            name: round(sum(r.scores[name].value for r in results) / len(results), 4)
            for name in results[0].scores
        } if results else {}
        return cls(
            generated_at=datetime.now(timezone.utc).isoformat(),
            dataset=dataset,
            task_count=len(results),
            pass_count=sum(r.passed for r in results),
            overall=round(sum(r.overall for r in results) / len(results), 4) if results else 0,
            dimensions=dimensions,
            results=results,
        )

