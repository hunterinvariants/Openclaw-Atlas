from __future__ import annotations

from .models import TaskSpec, Trace
from .simulator import DeterministicAgent


def replay(task: TaskSpec, original: Trace) -> tuple[Trace, bool]:
    replayed = DeterministicAgent().run(task)
    return replayed, replayed.digest == original.digest

