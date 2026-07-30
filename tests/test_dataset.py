from pathlib import Path

import pytest

from openclaw_atlas.io import load_tasks

DATASET = Path("datasets/milestone-1.jsonl")


def test_milestone_has_twenty_tasks_plus_three_controls() -> None:
    tasks = load_tasks(DATASET)
    assert len(tasks) == 23
    assert len({task.id for task in tasks}) == 23


def test_rejects_duplicate_ids(tmp_path: Path) -> None:
    line = DATASET.read_text(encoding="utf-8").splitlines()[0]
    path = tmp_path / "duplicate.jsonl"
    path.write_text(f"{line}\n{line}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        load_tasks(path)
