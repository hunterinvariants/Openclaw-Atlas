from __future__ import annotations

from pathlib import Path

from .io import load_tasks, write_json, write_trace
from .models import EvaluationReport
from .scoring import score
from .simulator import DeterministicAgent


class EvaluationRunner:
    def run(self, dataset: Path, evidence_dir: Path) -> EvaluationReport:
        tasks = load_tasks(dataset)
        results = []
        for task in tasks:
            trace = DeterministicAgent().run(task)
            write_trace(evidence_dir / "traces" / f"{task.id}.json", trace)
            results.append(score(task, trace))
        report = EvaluationReport.create(str(dataset.as_posix()), results)
        write_json(evidence_dir / "report.json", report.model_dump(mode="json"))
        (evidence_dir / "report.md").write_text(self.to_markdown(report), encoding="utf-8")
        return report

    @staticmethod
    def to_markdown(report: EvaluationReport) -> str:
        rows = "\n".join(
            f"| {result.task_id} | {result.overall:.2f} | {'PASS' if result.passed else 'FAIL'} |"
            for result in report.results
        )
        dimensions = "\n".join(f"- {name}: {value:.2f}" for name, value in report.dimensions.items())
        return (
            "# OPENCLAW-ATLAS Evaluation Report\n\n"
            f"- Dataset: `{report.dataset}`\n"
            f"- Tasks: {report.task_count}\n"
            f"- Passed: {report.pass_count}\n"
            f"- Overall: {report.overall:.2f}\n\n"
            "## Dimension averages\n\n"
            f"{dimensions}\n\n"
            "## Results\n\n"
            "| Task | Overall | Status |\n|---|---:|---|\n"
            f"{rows}\n"
        )

