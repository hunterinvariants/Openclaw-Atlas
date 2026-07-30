from pathlib import Path

from openclaw_atlas.io import load_tasks
from openclaw_atlas.runner import EvaluationRunner

DATASET = Path("datasets/milestone-1.jsonl")


def test_full_milestone_generates_report_and_traces(tmp_path: Path) -> None:
    tasks = load_tasks(DATASET)
    expected_passes = sum(task.expected_pass for task in tasks)
    report = EvaluationRunner().run(DATASET, tmp_path)
    assert report.task_count == len(tasks)
    assert report.pass_count == expected_passes
    assert report.expected_outcomes_matched == len(tasks)
    assert (tmp_path / "report.json").exists()
    assert (tmp_path / "report.md").exists()
    assert len(list((tmp_path / "traces").glob("*.json"))) == len(tasks)
