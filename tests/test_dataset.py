from pathlib import Path

import pytest

from openclaw_atlas.io import load_tasks

DATASET = Path("datasets/milestone-1.jsonl")


def test_milestone_ids_are_unique_and_controls_are_present() -> None:
    tasks = load_tasks(DATASET)
    assert len({task.id for task in tasks}) == len(tasks)
    controls = [task for task in tasks if not task.expected_pass]
    assert len(controls) >= 4, "the suite must keep failing controls"
    assert any(len(task.workflow) >= 5 for task in tasks), "needs deep workflows"


def test_rejects_duplicate_ids(tmp_path: Path) -> None:
    line = DATASET.read_text(encoding="utf-8").splitlines()[0]
    path = tmp_path / "duplicate.jsonl"
    path.write_text(f"{line}\n{line}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        load_tasks(path)


def test_prompt_injection_task_exposes_forbidden_distractor() -> None:
    task = next(
        task
        for task in load_tasks(DATASET)
        if task.id == "injected-instruction-resistance"
    )
    assert len(task.workflow) == 3
    assert task.fault and task.fault.kind.value == "injected_instruction"
    assert task.tool_catalog[0].tool == "admin.delete"
    assert "admin.delete" in task.policy.forbidden_tools


def test_controls_use_default_thresholds() -> None:
    controls = [task for task in load_tasks(DATASET) if not task.expected_pass]
    assert all(task.pass_threshold == 0.8 for task in controls)
