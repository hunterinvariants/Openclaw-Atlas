"""Versioned prompts and executable agent adapter contracts."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Protocol, cast

from .environment import FakeToolEnvironment, ToolFailure
from .models import TaskSpec, Trace, TraceEvent, WorkflowStep
from .simulator import DeterministicAgent, NaiveAgent

EFFORT_LEVELS = frozenset({"low", "medium", "high", "xhigh", "max"})


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
        return sha256(
            f"{self.name}:{self.version}:{self.template}".encode()
        ).hexdigest()


class AgentAdapter(Protocol):
    adapter_id: str

    def provenance(self) -> dict[str, Any]: ...
    async def run(self, task: TaskSpec, prompt: PromptTemplate) -> Trace: ...


class ReferenceAdapter:
    adapter_id = "deterministic-reference"

    def provenance(self) -> dict[str, Any]:
        return {"adapter": self.adapter_id, "deterministic": True}

    async def run(self, task: TaskSpec, prompt: PromptTemplate) -> Trace:
        prompt.render(task)
        agent = (
            NaiveAgent() if task.reference_agent == "naive" else DeterministicAgent()
        )
        return agent.run(task)


class CallableAdapter:
    def __init__(
        self, adapter_id: str, invoke: Callable[[TaskSpec, str], Awaitable[Trace]]
    ) -> None:
        self.adapter_id, self._invoke = adapter_id, invoke

    def provenance(self) -> dict[str, Any]:
        return {"adapter": self.adapter_id}

    async def run(self, task: TaskSpec, prompt: PromptTemplate) -> Trace:
        trace = await self._invoke(task, prompt.render(task))
        if trace.task_id != task.id:
            raise ValueError("adapter returned trace for wrong task")
        return trace.model_copy(update={"adapter_id": self.adapter_id})


class AnthropicMessagesAdapter:
    """Messages API tool loop with bounded retries and honest usage capture.

    Sampling parameters are deliberately absent: ``temperature`` / ``top_p`` /
    ``top_k`` are rejected by Claude Opus 5 and its siblings. Reasoning depth is
    controlled with ``effort``, and thinking is left at the model default
    (adaptive) — disabling it makes the model occasionally emit a tool call as
    plain text, which a tool-use evaluation must never silently absorb.
    """

    def __init__(
        self,
        model: str = "claude-opus-5",
        *,
        client: Any | None = None,
        max_rounds: int = 8,
        max_retries: int = 4,
        max_tokens: int = 8192,
        effort: str | None = "medium",
        input_cost_per_million: float | None = 5.0,
        output_cost_per_million: float | None = 25.0,
    ) -> None:
        if min(max_rounds, max_retries + 1) < 1:
            raise ValueError("round and retry limits must be non-negative")
        if max_tokens < 1:
            raise ValueError("max_tokens must be positive")
        if effort is not None and effort not in EFFORT_LEVELS:
            raise ValueError(f"effort must be one of {sorted(EFFORT_LEVELS)}")
        if client is None:
            try:
                from anthropic import AsyncAnthropic
            except ImportError as exc:
                raise RuntimeError("install openclaw-atlas[anthropic]") from exc
            client = AsyncAnthropic()
        self.client, self.model = client, model
        self.max_rounds, self.max_retries = max_rounds, max_retries
        self.max_tokens, self.effort = max_tokens, effort
        self.input_cost_per_million = input_cost_per_million
        self.output_cost_per_million = output_cost_per_million
        self.adapter_id = f"anthropic-messages:{model}"

    def provenance(self) -> dict[str, Any]:
        return {
            "adapter": self.adapter_id,
            "model": self.model,
            "sampling": {
                "effort": self.effort,
                "thinking": "model-default (adaptive)",
                "note": "temperature/top_p/top_k are rejected by this model family",
            },
            "max_tokens": self.max_tokens,
            "max_rounds": self.max_rounds,
            "max_retries": self.max_retries,
            "pricing_usd_per_million_tokens": {
                "input": self.input_cost_per_million,
                "output": self.output_cost_per_million,
            },
        }

    async def _create(self, **kwargs: Any) -> Any:
        for attempt in range(self.max_retries + 1):
            try:
                return await self.client.messages.create(**kwargs)
            except Exception as exc:
                status = getattr(exc, "status_code", None)
                if attempt == self.max_retries or (
                    status is not None
                    and status not in {408, 409, 429}
                    and status < 500
                ):
                    raise
                await asyncio.sleep(min(8.0, 0.5 * (2**attempt)))
        raise AssertionError("unreachable")

    async def run(self, task: TaskSpec, prompt: PromptTemplate) -> Trace:
        environment: FakeToolEnvironment = FakeToolEnvironment(task)
        events: list[TraceEvent] = []
        messages: list[dict[str, Any]] = [{"role": "user", "content": task.prompt}]
        sequence, next_step = 0, 0
        catalog = _unique_steps([*task.workflow, *task.tool_catalog])
        tools = [_tool_definition(step) for step in catalog]
        usage: dict[str, int | float] = {}
        for _ in range(self.max_rounds):
            kwargs: dict[str, Any] = {
                "model": self.model,
                "max_tokens": self.max_tokens,
                "system": prompt.render(task),
                "messages": messages,
                "tools": cast(Any, tools),
            }
            if self.effort is not None:
                kwargs["output_config"] = {"effort": self.effort}
            response = await self._create(**kwargs)
            _merge_usage(usage, getattr(response, "usage", None))
            stop_reason = str(getattr(response, "stop_reason", "") or "")
            blocks = list(getattr(response, "content", []))
            if stop_reason == "refusal":
                return self._terminal(
                    task,
                    events,
                    sequence,
                    usage,
                    "Model refused the request.",
                    "failed",
                )
            calls = [b for b in blocks if getattr(b, "type", "") == "tool_use"]
            if stop_reason == "max_tokens" and not calls:
                # Truncated mid-turn. Scoring this as a wrong answer would blame
                # the model for a budget we imposed, so name it explicitly.
                return self._terminal(
                    task,
                    events,
                    sequence,
                    usage,
                    f"Truncated: hit max_tokens={self.max_tokens} before completing.",
                    "failed",
                )
            if not calls:
                answer = _answer_text(blocks)
                return self._terminal(
                    task,
                    events,
                    sequence,
                    usage,
                    answer or "Model returned no final answer.",
                    "completed" if answer else "failed",
                )
            # Thinking and tool_use blocks must be echoed back unchanged.
            messages.append({"role": "assistant", "content": blocks})
            results: list[dict[str, Any]] = []
            for call in calls:
                tool = str(call.name)
                arguments = dict(getattr(call, "input", {}) or {})
                try:
                    step_index = _find_step(task, tool, next_step)
                except ValueError:
                    events.extend(
                        [
                            TraceEvent(
                                sequence=sequence,
                                kind="tool_call",
                                tool=tool,
                                arguments=arguments,
                            ),
                            TraceEvent(
                                sequence=sequence + 1,
                                kind="tool_result",
                                tool=tool,
                                error="undeclared_tool",
                            ),
                        ]
                    )
                    sequence += 2
                    results.append(
                        _tool_result(call.id, {"ok": False, "error": "undeclared_tool"})
                    )
                    continue
                step, attempt = (
                    task.workflow[step_index],
                    environment.attempts.get(step_index, 0) + 1,
                )
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
                    output = {"ok": False, "error": "argument_mismatch"}
                else:
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
                results.append(_tool_result(call.id, output))
            # All results for one assistant turn go back in a single user message.
            messages.append({"role": "user", "content": results})
        return self._terminal(
            task,
            events,
            sequence,
            usage,
            "Model exceeded the tool-call round limit.",
            "failed",
        )

    def _terminal(
        self,
        task: TaskSpec,
        events: list[TraceEvent],
        sequence: int,
        usage: dict[str, int | float],
        answer: str,
        status: str,
    ) -> Trace:
        events.append(TraceEvent(sequence=sequence, kind="final", result=answer))
        return Trace(
            task_id=task.id,
            events=events,
            final_answer=answer,
            status=cast(Any, status),
            adapter_id=self.adapter_id,
            usage=usage,
        )


class PromptRegistry:
    def __init__(self, prompts: list[PromptTemplate]) -> None:
        self._prompts = {(p.name, p.version): p for p in prompts}
        if len(self._prompts) != len(prompts):
            raise ValueError("duplicate prompt name/version")

    def get(self, name: str, version: str) -> PromptTemplate:
        try:
            return self._prompts[(name, version)]
        except KeyError as exc:
            raise KeyError(f"unknown prompt {name}@{version}") from exc

    @classmethod
    def from_json(cls, path: Path) -> PromptRegistry:
        return cls(
            [
                PromptTemplate(**row)
                for row in json.loads(path.read_text(encoding="utf-8-sig"))
            ]
        )


USAGE_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
)


def _merge_usage(target: dict[str, int | float], usage: Any) -> None:
    if usage is None:
        return
    for key in USAGE_FIELDS:
        value = getattr(usage, key, None)
        if isinstance(value, (int, float)):
            target[key] = target.get(key, 0) + value


def _answer_text(blocks: list[Any]) -> str:
    return "\n".join(
        str(getattr(block, "text", ""))
        for block in blocks
        if getattr(block, "type", "") == "text"
    ).strip()


def _tool_result(tool_use_id: str, output: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "tool_result",
        "tool_use_id": str(tool_use_id),
        "content": json.dumps(output, sort_keys=True),
        "is_error": not output.get("ok", False),
    }


def _unique_steps(steps: list[WorkflowStep]) -> list[WorkflowStep]:
    return list({s.tool: s for s in steps}.values())


def _tool_definition(step: WorkflowStep) -> dict[str, Any]:
    properties = {
        name: {"type": _json_type(value)} for name, value in step.arguments.items()
    }
    return {
        "name": step.tool,
        "description": f"Evaluation tool: {step.tool}",
        "input_schema": {
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
    raise ValueError(f"model called undeclared tool {tool!r}")
