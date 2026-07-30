from __future__ import annotations

import json
from pathlib import Path

from .models import TaskSpec, Trace


def load_tasks(path: Path) -> list[TaskSpec]:
    tasks: list[TaskSpec] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if line.strip():
                try:
                    tasks.append(TaskSpec.model_validate_json(line))
                except Exception as exc:
                    raise ValueError(f"{path}:{line_number}: invalid task: {exc}") from exc
    ids = [task.id for task in tasks]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{path}: duplicate task IDs")
    return tasks


def write_trace(path: Path, trace: Trace) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(trace.model_dump_json(indent=2) + "\n", encoding="utf-8")


def read_trace(path: Path) -> Trace:
    return Trace.model_validate_json(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")

