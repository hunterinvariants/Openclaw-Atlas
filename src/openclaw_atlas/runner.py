from __future__ import annotations

import asyncio
from hashlib import sha256
from pathlib import Path
from typing import Any

from .adapters import AgentAdapter, PromptTemplate, ReferenceAdapter
from .io import load_tasks, read_trace, write_json, write_trace
from .models import EvaluationReport, EvaluationResult, TaskSpec, Trace
from .scoring import score
from .simulator import DeterministicAgent, NaiveAgent
from .stability import STABILITY_METHOD, STABILITY_WEIGHTS, stability_score

DEFAULT_REPETITIONS = 3


def _reject_pinned_controls(tasks: list[TaskSpec], adapter: AgentAdapter) -> None:
    """Agent-pinned controls are scorer unit tests, not model-facing tasks.

    ``reference_agent: "naive"`` exists to make a scorer fire; a real adapter
    that behaves correctly would score PASS against ``expected_pass: false`` and
    fail the run for the wrong reason. Refuse the dataset instead.
    """
    if adapter.adapter_id == ReferenceAdapter.adapter_id:
        return
    pinned = sorted(t.id for t in tasks if t.reference_agent != "deterministic")
    if pinned:
        raise ValueError(
            f"{', '.join(pinned)} pin a reference agent and cannot be evaluated with "
            f"adapter {adapter.adapter_id!r}; run them with --adapter reference"
        )


class EvaluationRunner:
    def run(
        self, dataset: Path, evidence_dir: Path, *, resume: bool = False
    ) -> EvaluationReport:
        tasks, adapter = load_tasks(dataset), ReferenceAdapter()
        results = []
        for task in tasks:
            cache = evidence_dir / "runs" / task.id / "1.json"
            if resume and cache.exists():
                trace = read_trace(cache)
            else:
                agent = (
                    NaiveAgent()
                    if task.reference_agent == "naive"
                    else DeterministicAgent()
                )
                trace = agent.run(task)
                write_trace(cache, trace)
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
        resume: bool = False,
    ) -> EvaluationReport:
        if repetitions < 1 or concurrency < 1:
            raise ValueError("repetitions and concurrency must be positive")
        tasks = load_tasks(dataset)
        _reject_pinned_controls(tasks, adapter)
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
        partial = EvaluationReport.create(dataset.as_posix(), results)
        write_json(
            evidence_dir / "checkpoint.json",
            {
                "artifact_kind": "incomplete_checkpoint",
                "completed_tasks": len(results),
                "report": partial.model_dump(mode="json"),
            },
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
        usage: dict[str, float] = {}
        paths: list[Path] = []
        for result in report.results:
            run_paths = [
                evidence_dir / "runs" / result.task_id / f"{index + 1}.json"
                for index in range(repetitions)
            ]
            existing = [path for path in run_paths if path.exists()]
            paths.extend(
                existing
                if existing
                else [evidence_dir / "traces" / f"{result.task_id}.json"]
            )
        for path in paths:
            for key, value in read_trace(path).usage.items():
                usage[key] = usage.get(key, 0.0) + float(value)
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
