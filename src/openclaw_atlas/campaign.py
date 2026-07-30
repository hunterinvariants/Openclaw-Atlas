"""Systematic fault-injection campaigns over task workflows."""

from __future__ import annotations

from dataclasses import dataclass

from .models import FaultKind, FaultSpec, TaskSpec
from .scoring import score
from .simulator import DeterministicAgent


@dataclass(frozen=True)
class CampaignCase:
    task_id: str
    step: int
    fault: str
    status: str
    passed: bool
    overall: float


@dataclass(frozen=True)
class CampaignReport:
    cases: list[CampaignCase]

    @property
    def pass_rate(self) -> float:
        if not self.cases:
            return 0.0
        return round(sum(case.passed for case in self.cases) / len(self.cases), 4)


def run_campaign(
    tasks: list[TaskSpec],
    faults: tuple[FaultKind, ...] = (
        FaultKind.timeout,
        FaultKind.malformed_response,
        FaultKind.stale_data,
    ),
) -> CampaignReport:
    cases: list[CampaignCase] = []
    agent = DeterministicAgent()
    for task in tasks:
        if not task.expected_pass:
            continue
        for step in range(len(task.workflow)):
            for fault in faults:
                variant = task.model_copy(
                    update={
                        "id": f"{task.id}::{step}::{fault.value}",
                        "fault": FaultSpec(step=step, kind=fault, attempts=1),
                        "retry_limit": max(1, task.retry_limit),
                        "max_tool_calls": max(
                            task.max_tool_calls, len(task.workflow) + 1
                        ),
                    }
                )
                trace = agent.run(variant)
                result = score(variant, trace)
                cases.append(
                    CampaignCase(
                        task_id=task.id,
                        step=step,
                        fault=fault.value,
                        status=trace.status,
                        passed=result.passed,
                        overall=result.overall,
                    )
                )
    return CampaignReport(cases)
