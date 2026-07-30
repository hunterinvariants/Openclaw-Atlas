from __future__ import annotations

import json
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "1.0"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FaultKind(StrEnum):
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


class PolicySpec(StrictModel):
    forbidden_tools: list[str] = Field(default_factory=list)
    max_tool_calls: int | None = Field(default=None, ge=0)
    sensitive_argument_keys: list[str] = Field(
        default_factory=lambda: ["password", "secret", "token", "api_key"]
    )
    require_permission_before_mutation: bool = False


class TaskSpec(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    id: str
    title: str
    prompt: str
    workflow: list[WorkflowStep]
    expected_answer_contains: list[str]
    max_tool_calls: int = Field(ge=0)
    retry_limit: int = Field(default=1, ge=0, le=5)
    fault: FaultSpec | None = None
    policy: PolicySpec = Field(default_factory=PolicySpec)
    pass_threshold: float = Field(default=0.8, ge=0, le=1)
    expected_pass: bool = True
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
    schema_version: Literal["1.0"] = "1.0"
    task_id: str
    events: list[TraceEvent]
    final_answer: str
    status: Literal["completed", "failed", "blocked"]
    adapter_id: str = "deterministic-reference"

    def canonical_payload(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        )

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
    expected_pass: bool = True
    outcome_matched: bool = True
    policy_violations: list[str] = Field(default_factory=list)


class EvaluationReport(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    generated_at: str
    dataset: str
    task_count: int
    pass_count: int
    overall: float
    dimensions: dict[str, float]
    results: list[EvaluationResult]
    expected_outcomes_matched: int = 0

    @classmethod
    def create(cls, dataset: str, results: list[EvaluationResult]) -> EvaluationReport:
        dimensions = (
            {
                name: round(
                    sum(result.scores[name].value for result in results) / len(results),
                    4,
                )
                for name in results[0].scores
            }
            if results
            else {}
        )
        return cls(
            generated_at=datetime.now(UTC).isoformat(),
            dataset=dataset,
            task_count=len(results),
            pass_count=sum(result.passed for result in results),
            overall=(
                round(sum(result.overall for result in results) / len(results), 4)
                if results
                else 0
            ),
            dimensions=dimensions,
            results=results,
            expected_outcomes_matched=sum(result.outcome_matched for result in results),
        )
