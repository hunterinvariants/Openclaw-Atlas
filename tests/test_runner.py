from pathlib import Path

from openclaw_atlas.runner import EvaluationRunner


def test_full_milestone_generates_report_and_traces(tmp_path: Path) -> None:
    report = EvaluationRunner().run(Path("datasets/milestone-1.jsonl"), tmp_path)
    assert report.task_count == 20
    assert report.pass_count == 20
    assert report.overall == 1
    assert (tmp_path / "report.json").exists()
    assert (tmp_path / "report.md").exists()
    assert len(list((tmp_path / "traces").glob("*.json"))) == 20

