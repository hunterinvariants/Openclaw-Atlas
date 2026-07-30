"""Versioned prompt and model adapter contracts."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Awaitable, Callable, Protocol
from .models import TaskSpec, Trace
from .simulator import DeterministicAgent

@dataclass(frozen=True)
class PromptTemplate:
    name: str
    version: str
    template: str
    def render(self, task: TaskSpec) -> str:
        return self.template.format(task_id=task.id, title=task.title, prompt=task.prompt)
    @property
    def digest(self) -> str:
        return sha256(f"{self.name}:{self.version}:{self.template}".encode()).hexdigest()

class AgentAdapter(Protocol):
    adapter_id: str
    async def run(self, task: TaskSpec, prompt: PromptTemplate) -> Trace: ...

class ReferenceAdapter:
    adapter_id = "deterministic-reference"
    async def run(self, task: TaskSpec, prompt: PromptTemplate) -> Trace:
        prompt.render(task)
        return DeterministicAgent().run(task)

class CallableAdapter:
    """Wrap any async model client without coupling ATLAS to a vendor SDK."""
    def __init__(self, adapter_id: str, invoke: Callable[[TaskSpec, str], Awaitable[Trace]]):
        self.adapter_id, self._invoke = adapter_id, invoke
    async def run(self, task: TaskSpec, prompt: PromptTemplate) -> Trace:
        trace = await self._invoke(task, prompt.render(task))
        if trace.task_id != task.id: raise ValueError("adapter returned trace for wrong task")
        return trace

class PromptRegistry:
    def __init__(self, prompts: list[PromptTemplate]):
        self._prompts = {(p.name, p.version): p for p in prompts}
        if len(self._prompts) != len(prompts): raise ValueError("duplicate prompt name/version")
    def get(self, name: str, version: str) -> PromptTemplate:
        try: return self._prompts[(name, version)]
        except KeyError as exc: raise KeyError(f"unknown prompt {name}@{version}") from exc
    @classmethod
    def from_json(cls, path):
        rows=json.loads(path.read_text(encoding="utf-8-sig"))
        return cls([PromptTemplate(**row) for row in rows])
