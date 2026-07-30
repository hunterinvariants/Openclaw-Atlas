from __future__ import annotations

import asyncio
from hashlib import sha256
from pathlib import Path
from typing import Any

from .adapters import AgentAdapter, PromptTemplate, ReferenceAdapter
from .io import load_tasks, read_trace, write_json, write_trace
from .models import EvaluationReport, EvaluationResult, TaskSpec, Trace
from .scoring import score
from .stability import STABILITY_METHOD, STABILITY_WEIGHTS, stability_score

DEFAULT_REPETITIONS = 3


class EvaluationRunner:
    def run(self, dataset: Path, evidence_dir: Path) -> EvaluationReport:
        tasks, adapter = load_tasks(dataset), ReferenceAdapter()
        results = []
        for task in tasks:
            trace = (
                read_trace(evidence_dir / "traces" / f"{task.id}.json")
                if (evidence_dir / "traces" / f"{task.id}.json").exists()
                else None
            )
            trace = trace or __import__(
                "openclaw_atlas.simulator", fromlist=["DeterministicAgent"]
            ).DeterministicAgent().run(task)
            self._persist_trace(evidence_dir, trace)
            results.append(score(task, trace, reproducibility=1.0))
            self._checkpoint(evidence_dir, dataset, results)
        report = EvaluationReport.create(dataset.as_posix(), results)
        self._write(evidence_dir, report)
        self._write_provenance(
            evidence_dir, dataset, adapter.provenance(), None, 1, report
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
        concurrency: int = 4,
        resume: bool = True,
    ) -> EvaluationReport:
        if repetitions < 1 or concurrency < 1:
            raise ValueError("repetitions and concurrency must be positive")
        tasks = load_tasks(dataset)
        semaphore = asyncio.Semaphore(concurrency)

        async def evaluate(task: TaskSpec) -> EvaluationResult:
            async with semaphore:
                run_dir = evidence_dir / "runs" / task.id
                traces: list[Trace] = []
                for index in range(repetitions):
                    path = run_dir / f"{index + 1}.json"
                    if resume and path.exists():
                        trace = read_trace(path)
                    else:
                        trace = await adapter.run(task, prompt)
                        write_trace(path, trace)
                    traces.append(trace)
                self._persist_trace(evidence_dir, traces[0])
                return score(task, traces[0], reproducibility=stability_score(traces))

        pending = [asyncio.create_task(evaluate(task)) for task in tasks]
        results = []
        for future in asyncio.as_completed(pending):
            results.append(await future)
            self._checkpoint(evidence_dir, dataset, results)
        order = {task.id: index for index, task in enumerate(tasks)}
        results.sort(key=lambda item: order[item.task_id])
        report = EvaluationReport.create(dataset.as_posix(), results)
        self._write(evidence_dir, report)
        self._write_provenance(
            evidence_dir, dataset, adapter.provenance(), prompt, repetitions, report
        )
        return report

    @staticmethod
    def outcomes_match(report: EvaluationReport) -> bool:
        return report.expected_outcomes_matched == report.task_count

    @staticmethod
    def _persist_trace(evidence_dir: Path, trace: Trace) -> None:
        write_trace(evidence_dir / "traces" / f"{trace.task_id}.json", trace)

    def _checkpoint(
        self, evidence_dir: Path, dataset: Path, results: list[EvaluationResult]
    ) -> None:
        write_json(
            evidence_dir / "checkpoint.json",
            EvaluationReport.create(dataset.as_posix(), results).model_dump(
                mode="json"
            ),
        )

    def _write(self, evidence_dir: Path, report: EvaluationReport) -> None:
        write_json(evidence_dir / "report.json", report.model_dump(mode="json"))
        (evidence_dir / "report.md").write_text(
            self.to_markdown(report), encoding="utf-8"
        )
        (evidence_dir / "checkpoint.json").unlink(missing_ok=True)

    @staticmethod
    def _write_provenance(
        evidence_dir: Path,
        dataset: Path,
        adapter: dict[str, Any],
        prompt: PromptTemplate | None,
        repetitions: int,
        report: EvaluationReport,
    ) -> None:
        usage = {
            key: sum(
                float(r)
                for trace in (evidence_dir / "traces").glob("*.json")
                for key, r in read_trace(trace).usage.items()
            )
            for key in {
                k
                for trace in (evidence_dir / "traces").glob("*.json")
                for k in read_trace(trace).usage
            }
        }
        pricing = adapter.get("pricing_usd_per_million_tokens", {})
        input_rate = pricing.get("input")
        output_rate = pricing.get("output")
        estimated_cost = None
        if input_rate is not None and output_rate is not None:
            estimated_cost = round(
                (
                    usage.get("input_tokens", 0) * input_rate
                    + usage.get("output_tokens", 0) * output_rate
                )
                / 1_000_000,
                8,
            )
        write_json(
            evidence_dir / "provenance.json",
            {
                **adapter,
                "dataset_digest": sha256(dataset.read_bytes()).hexdigest(),
                "prompt": f"{prompt.name}@{prompt.version}" if prompt else None,
                "prompt_digest": prompt.digest if prompt else None,
                "repetitions": repetitions,
                "stability_method": STABILITY_METHOD,
                "stability_weights": STABILITY_WEIGHTS,
                "usage": usage,
                "estimated_cost_usd": estimated_cost,
                "tasks": report.task_count,
            },
        )

    @staticmethod
    def to_markdown(report: EvaluationReport) -> str:
        rows = "\n".join(_result_row(r) for r in report.results)
        dimensions = "\n".join(f"- {n}: {v:.2f}" for n, v in report.dimensions.items())
        return (
            "# OPENCLAW-ATLAS Evaluation Report\n\n"
            f"- Dataset: `{report.dataset}`\n- Tasks: {report.task_count}\n"
            f"- Actual passes: {report.pass_count}\n"
            f"- Expected outcomes matched: {report.expected_outcomes_matched}/"
            f"{report.task_count}\n- Overall: {report.overall:.2f}\n\n"
            f"## Dimension averages\n\n{dimensions}\n\n## Results\n\n"
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
