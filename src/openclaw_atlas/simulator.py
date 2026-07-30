from __future__ import annotations

from .environment import FakeToolEnvironment, ToolFailure
from .models import FaultKind, TaskSpec, Trace, TraceEvent


RETRYABLE = {FaultKind.timeout, FaultKind.malformed_response, FaultKind.stale_data}


class DeterministicAgent:
    """Executes a declared workflow, providing a stable evaluation target."""

    def run(self, task: TaskSpec) -> Trace:
        environment = FakeToolEnvironment(task)
        events: list[TraceEvent] = []
        sequence = 0
        outputs: list[str] = []

        for step_index, step in enumerate(task.workflow):
            attempt = 0
            while True:
                attempt += 1
                events.append(TraceEvent(
                    sequence=sequence, kind="tool_call", tool=step.tool,
                    arguments=step.arguments, attempt=attempt,
                ))
                sequence += 1
                try:
                    result = environment.call(step_index, step)
                    events.append(TraceEvent(
                        sequence=sequence, kind="tool_result", tool=step.tool,
                        result=result, attempt=attempt,
                    ))
                    sequence += 1
                    outputs.append(self._render(result))
                    break
                except ToolFailure as exc:
                    events.append(TraceEvent(
                        sequence=sequence, kind="tool_result", tool=step.tool,
                        error=exc.kind.value, attempt=attempt,
                    ))
                    sequence += 1
                    if exc.kind == FaultKind.permission_denied:
                        answer = "Blocked safely: permission denied."
                        events.append(TraceEvent(sequence=sequence, kind="final", result=answer))
                        return Trace(task_id=task.id, events=events, final_answer=answer, status="blocked")
                    if exc.kind not in RETRYABLE or attempt > task.retry_limit:
                        answer = f"Failed safely: {exc.kind.value}."
                        events.append(TraceEvent(sequence=sequence, kind="final", result=answer))
                        return Trace(task_id=task.id, events=events, final_answer=answer, status="failed")

        answer = " | ".join(outputs)
        events.append(TraceEvent(sequence=sequence, kind="final", result=answer))
        return Trace(task_id=task.id, events=events, final_answer=answer, status="completed")

    @staticmethod
    def _render(value: object) -> str:
        if isinstance(value, dict):
            return ", ".join(f"{key}={value[key]}" for key in sorted(value))
        if isinstance(value, list):
            return ", ".join(map(str, value))
        return str(value)

