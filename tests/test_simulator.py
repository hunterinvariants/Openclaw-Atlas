from pathlib import Path

from openclaw_atlas.io import load_tasks
from openclaw_atlas.models import FaultKind
from openclaw_atlas.replay import replay
from openclaw_atlas.scoring import DIMENSIONS, score
from openclaw_atlas.simulator import DeterministicAgent


TASKS = {task.id: task for task in load_tasks(Path("datasets/milestone-1.jsonl"))}


def test_trace_replay_is_byte_stable() -> None:
    task = TASKS["two-source-summary"]
    trace = DeterministicAgent().run(task)
    replayed, stable = replay(task, trace)
    assert stable
    assert replayed.canonical_payload() == trace.canonical_payload()


def test_timeout_is_retried_once() -> None:
    task = TASKS["timeout-recovery"]
    trace = DeterministicAgent().run(task)
    assert trace.status == "completed"
    assert sum(event.kind == "tool_call" for event in trace.events) == 2
    assert any(event.error == FaultKind.timeout.value for event in trace.events)


def test_permission_failure_blocks_mutation() -> None:
    task = TASKS["permission-block"]
    trace = DeterministicAgent().run(task)
    result = score(task, trace)
    assert trace.status == "blocked"
    assert result.scores["safety"].value == 1
    assert result.passed


def test_all_five_dimensions_are_scored() -> None:
    task = TASKS["lookup-customer-tier"]
    result = score(task, DeterministicAgent().run(task))
    assert tuple(result.scores) == DIMENSIONS
    assert result.overall == 1

