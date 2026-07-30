"""Versioned prompts and executable agent adapter contracts."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Protocol, cast

from .environment import FakeToolEnvironment, ToolFailure
from .models import TaskSpec, Trace, TraceEvent, WorkflowStep
from .simulator import DeterministicAgent


@dataclass(frozen=True)
class PromptTemplate:
    name: str
    version: str
    template: str

    def render(self, task: TaskSpec) -> str:
        return self.template.format(
            task_id=task.id, title=task.title, prompt=task.prompt
        )

    @property
    def digest(self) -> str:
        payload = f"{self.name}:{self.version}:{self.template}"
        return sha256(payload.encode()).hexdigest()


class AgentAdapter(Protocol):
    adapter_id: str

    async def run(self, task: TaskSpec, prompt: PromptTemplate) -> Trace: ...


class ReferenceAdapter:
    adapter_id = "deterministic-reference"

    async def run(self, task: TaskSpec, prompt: PromptTemplate) -> Trace:
        prompt.render(task)
        return DeterministicAgent().run(task)


class CallableAdapter:
    """Wrap a custom async adapter while preserving task/trace validation."""

    def __init__(
        self,
        adapter_id: str,
        invoke: Callable[[TaskSpec, str], Awaitable[Trace]],
    ) -> None:
        self.adapter_id = adapter_id
        self._invoke = invoke

    async def run(self, task: TaskSpec, prompt: PromptTemplate) -> Trace:
        trace = await self._invoke(task, prompt.render(task))
        if trace.task_id != task.id:
            raise ValueError("adapter returned trace for wrong task")
        return trace.model_copy(update={"adapter_id": self.adapter_id})


class OpenAIResponsesAdapter:
    """Execute real OpenAI tool calls against the deterministic environment.

    The OpenAI dependency is optional and imported only when a client is not
    injected. Tests use a protocol-compatible fake client; production use reads
    normal SDK configuration such as ``OPENAI_API_KEY``.
    """

    def __init__(
        self,
        model: str = "gpt-5-mini",
        *,
        client: Any | None = None,
        max_rounds: int = 8,
    ) -> None:
        if max_rounds < 1:
            raise ValueError("max_rounds must be positive")
        if client is None:
            try:
                from openai import AsyncOpenAI
            except ImportError as exc:
                raise RuntimeError(
                    "install openclaw-atlas[openai] to use the OpenAI adapter"
                ) from exc
            client = AsyncOpenAI()
        self.client = client
        self.model = model
        self.max_rounds = max_rounds
        self.adapter_id = f"openai-responses:{model}"

    async def run(self, task: TaskSpec, prompt: PromptTemplate) -> Trace:
        environment = FakeToolEnvironment(task)
        events: list[TraceEvent] = []
        sequence = 0
        next_step = 0
        inputs: list[Any] = [{"role": "user", "content": task.prompt}]
        tools = [_tool_definition(step) for step in _unique_steps(task.workflow)]

        for _ in range(self.max_rounds):
            response = await self.client.responses.create(
                model=self.model,
                instructions=prompt.render(task),
                input=inputs,
                tools=cast(Any, tools),
            )
            outputs = list(getattr(response, "output", []))
            calls = [
                item for item in outputs if getattr(item, "type", "") == "function_call"
            ]
            if not calls:
                answer = str(getattr(response, "output_text", "")).strip()
                status = cast(Any, "completed" if answer else "failed")
                if not answer:
                    answer = "Model returned no final answer."
                events.append(
                    TraceEvent(sequence=sequence, kind="final", result=answer)
                )
                return Trace(
                    task_id=task.id,
                    events=events,
                    final_answer=answer,
                    status=status,
                    adapter_id=self.adapter_id,
                )

            inputs.extend(outputs)
            for call in calls:
                arguments = json.loads(getattr(call, "arguments", "{}"))
                tool = str(call.name)
                step_index = _find_step(task, tool, next_step)
                step = task.workflow[step_index]
                attempt = environment.attempts.get(step_index, 0) + 1
                events.append(
                    TraceEvent(
                        sequence=sequence,
                        kind="tool_call",
                        tool=tool,
                        arguments=arguments,
                        attempt=attempt,
                    )
                )
                sequence += 1
                if arguments != step.arguments:
                    events.append(
                        TraceEvent(
                            sequence=sequence,
                            kind="tool_result",
                            tool=tool,
                            error="argument_mismatch",
                            attempt=attempt,
                        )
                    )
                    output = {
                        "ok": False,
                        "error": "argument_mismatch",
                        "expected_arguments": step.arguments,
                    }
                    sequence += 1
                    inputs.append(
                        {
                            "type": "function_call_output",
                            "call_id": str(call.call_id),
                            "output": json.dumps(output, sort_keys=True),
                        }
                    )
                    continue
                next_step = max(next_step, step_index + 1)
                try:
                    result = environment.call(step_index, step)
                    events.append(
                        TraceEvent(
                            sequence=sequence,
                            kind="tool_result",
                            tool=tool,
                            result=result,
                            attempt=attempt,
                        )
                    )
                    output = {"ok": True, "result": result}
                except ToolFailure as exc:
                    events.append(
                        TraceEvent(
                            sequence=sequence,
                            kind="tool_result",
                            tool=tool,
                            error=exc.kind.value,
                            attempt=attempt,
                        )
                    )
                    output = {"ok": False, "error": exc.kind.value}
                sequence += 1
                inputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": str(call.call_id),
                        "output": json.dumps(output, sort_keys=True),
                    }
                )

        answer = "Model exceeded the tool-call round limit."
        events.append(TraceEvent(sequence=sequence, kind="final", result=answer))
        return Trace(
            task_id=task.id,
            events=events,
            final_answer=answer,
            status="failed",
            adapter_id=self.adapter_id,
        )


class PromptRegistry:
    def __init__(self, prompts: list[PromptTemplate]) -> None:
        self._prompts = {(prompt.name, prompt.version): prompt for prompt in prompts}
        if len(self._prompts) != len(prompts):
            raise ValueError("duplicate prompt name/version")

    def get(self, name: str, version: str) -> PromptTemplate:
        try:
            return self._prompts[(name, version)]
        except KeyError as exc:
            raise KeyError(f"unknown prompt {name}@{version}") from exc

    @classmethod
    def from_json(cls, path: Path) -> PromptRegistry:
        rows = json.loads(path.read_text(encoding="utf-8-sig"))
        return cls([PromptTemplate(**row) for row in rows])


def _unique_steps(steps: list[WorkflowStep]) -> list[WorkflowStep]:
    return list({step.tool: step for step in steps}.values())


def _tool_definition(step: WorkflowStep) -> dict[str, Any]:
    properties = {
        name: {"type": _json_type(value)} for name, value in step.arguments.items()
    }
    return {
        "type": "function",
        "name": step.tool,
        "description": f"Deterministic evaluation tool: {step.tool}",
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": sorted(properties),
            "additionalProperties": False,
        },
        "strict": True,
    }


def _json_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "string"


def _find_step(task: TaskSpec, tool: str, start: int) -> int:
    for index in range(start, len(task.workflow)):
        if task.workflow[index].tool == tool:
            return index
    for index, step in enumerate(task.workflow):
        if step.tool == tool:
            return index
    raise ValueError(f"model called undeclared tool {tool!r}")
