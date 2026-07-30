from __future__ import annotations

from collections.abc import Callable

from .models import TaskSpec, Trace
from .simulator import DeterministicAgent

TraceExecutor = Callable[[TaskSpec], Trace]


def replay(
    task: TaskSpec,
    original: Trace,
    executor: TraceExecutor | None = None,
) -> tuple[Trace, bool]:
    """Replay with the same synchronous executor that produced the trace.

    Async and stochastic adapters use ``stability_score`` through the runner;
    this helper remains the exact-digest check for deterministic executors.
    """
    execute = executor or DeterministicAgent().run
    replayed = execute(task)
    return replayed, replayed.digest == original.digest
