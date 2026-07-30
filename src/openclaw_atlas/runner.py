from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from .adapters import AgentAdapter, PromptTemplate, ReferenceAdapter
from .io import load_tasks, write_json, write_trace
from .models import EvaluationReport, EvaluationResult, Trace
from .scoring import score
from .simulator import DeterministicAgent
from .stability import stability_score

DEFAULT_REPETITIONS = 3


class EvaluationRunner:
    def run(self, dataset: Path, evidence_dir: Path) -> EvaluationReport:
        tasks = load_tasks(dataset)
        adapter = ReferenceAdapter()
        results: list[EvaluationResult] = []
        for task in tasks:
            traces = [
                DeterministicAgent().run(task) for _ in range(DEFAULT_REPETITIONS)
            ]
            self._persist_trace(evidence_dir, traces[0])
            results.append(
                score(task, traces[0], reproducibility=stability_score(traces))
            )
        report = EvaluationReport.create(dataset.as_posix(), results)
        self._write(evidence_dir, report)
        self._write_provenance(
            evidence_dir,
            dataset,
            adapter.adapter_id,
            prompt=None,
            repetitions=DEFAULT_REPETITIONS,
        )
        return report

    async def run_adapter(
        self,
        dataset: Path,
        evidence_dir: Path,
        adapter: AgentAdapter,
        prompt: PromptTemplate,
        *,
        repetitions: int = DEFAULT_REPETITIONS,
    ) -> EvaluationReport:
        if repetitions < 1:
            raise ValueError("repetitions must be positive")
        tasks = load_tasks(dataset)
        results: list[EvaluationResult] = []
        for task in tasks:
            traces = [await adapter.run(task, prompt) for _ in range(repetitions)]
            self._persist_trace(evidence_dir, traces[0])
            results.append(
                score(task, traces[0], reproducibility=stability_score(traces))
            )
        report = EvaluationReport.create(dataset.as_posix(), results)
        self._write(evidence_dir, report)
        self._write_provenance(
            evidence_dir,
            dataset,
            adapter.adapter_id,
            prompt=prompt,
            repetitions=repetitions,
        )
        return report

    @staticmethod
    def outcomes_match(report: EvaluationReport) -> bool:
        return report.expected_outcomes_matched == report.task_count

    @staticmethod
    def _persist_trace(evidence_dir: Path, trace: Trace) -> None:
        write_trace(evidence_dir / "traces" / f"{trace.task_id}.json", trace)

    def _write(self, evidence_dir: Path, report: EvaluationReport) -> None:
        write_json(evidence_dir / "report.json", report.model_dump(mode="json"))
        (evidence_dir / "report.md").write_text(
            self.to_markdown(report), encoding="utf-8"
        )

    @staticmethod
    def _write_provenance(
        evidence_dir: Path,
        dataset: Path,
        adapter_id: str,
        *,
        prompt: PromptTemplate | None,
        repetitions: int,
    ) -> None:
        write_json(
            evidence_dir / "provenance.json",
            {
                "adapter": adapter_id,
                "dataset_digest": sha256(dataset.read_bytes()).hexdigest(),
                "prompt": f"{prompt.name}@{prompt.version}" if prompt else None,
                "prompt_digest": prompt.digest if prompt else None,
                "repetitions": repetitions,
                "stability_method": "structural-v1",
            },
        )

    @staticmethod
    def to_markdown(report: EvaluationReport) -> str:
        rows = "\n".join(_result_row(result) for result in report.results)
        dimensions = "\n".join(
            f"- {name}: {value:.2f}" for name, value in report.dimensions.items()
        )
        return (
            "# OPENCLAW-ATLAS Evaluation Report\n\n"
            f"- Dataset: `{report.dataset}`\n"
            f"- Tasks: {report.task_count}\n"
            f"- Actual passes: {report.pass_count}\n"
            f"- Expected outcomes matched: "
            f"{report.expected_outcomes_matched}/{report.task_count}\n"
            f"- Overall: {report.overall:.2f}\n\n"
            "## Dimension averages\n\n"
            f"{dimensions}\n\n"
            "## Results\n\n"
            "| Task | Overall | Actual | Expected | Validation |\n"
            "|---|---:|---|---|---|\n"
            f"{rows}\n"
        )


def _result_row(result: EvaluationResult) -> str:
    actual = "PASS" if result.passed else "FAIL"
    expected = "PASS" if result.expected_pass else "FAIL"
    validation = "MATCH" if result.outcome_matched else "MISMATCH"
    return (
        f"| {result.task_id} | {result.overall:.2f} | {actual} | "
        f"{expected} | {validation} |"
    )
