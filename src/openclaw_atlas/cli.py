from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict
from pathlib import Path

from .adapters import OpenAIResponsesAdapter, PromptRegistry, ReferenceAdapter
from .analytics import TraceStore
from .campaign import run_campaign
from .io import load_tasks, read_trace
from .query import CATALOG, QueryEngine
from .regression import Thresholds, compare
from .regression import load as load_report
from .replay import replay
from .review import analyze, load_labels, load_rubric, write_template
from .runner import EvaluationRunner


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="atlas")
    commands = root.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="run an evaluation suite")
    run.add_argument("dataset", type=Path)
    run.add_argument("--evidence-dir", type=Path, default=Path("evidence/latest"))
    run.add_argument("--adapter", choices=["reference", "openai"], default="reference")
    run.add_argument("--model", default="gpt-5-mini")
    run.add_argument("--prompt-registry", type=Path, default=Path("prompts.json"))
    run.add_argument("--prompt", default="tool-agent@2")
    run.add_argument("--repetitions", type=int, default=3)
    run.add_argument("--concurrency", type=int, default=4)
    run.add_argument("--no-resume", action="store_true")
    run.add_argument("--temperature", type=float)
    run.add_argument("--top-p", type=float)
    run.add_argument("--seed", type=int)
    run.add_argument("--max-rounds", type=int, default=8)
    run.add_argument("--max-retries", type=int, default=4)
    run.add_argument("--input-cost-per-million", type=float)
    run.add_argument("--output-cost-per-million", type=float)

    replay_command = commands.add_parser("replay", help="exact deterministic replay")
    replay_command.add_argument("dataset", type=Path)
    replay_command.add_argument("trace", type=Path)

    compare_command = commands.add_parser("compare", help="gate against a baseline")
    compare_command.add_argument("baseline", type=Path)
    compare_command.add_argument("candidate", type=Path)
    compare_command.add_argument("--max-overall-drop", type=float, default=0.02)
    compare_command.add_argument("--max-dimension-drop", type=float, default=0.05)
    compare_command.add_argument("--allow-new-failures", type=int, default=0)

    ingest = commands.add_parser("ingest", help="ingest evidence into SQLite")
    ingest.add_argument("report", type=Path)
    ingest.add_argument("traces", type=Path)
    ingest.add_argument("database", type=Path)
    ingest.add_argument("--labels", type=Path)

    query = commands.add_parser("query", help="run a named read-only query")
    query.add_argument("database", type=Path)
    query.add_argument("name", choices=sorted(CATALOG))
    query.add_argument("--run-id", type=int, default=1)
    query.add_argument("--backend", choices=["sqlite", "duckdb"], default="sqlite")

    campaign = commands.add_parser("campaign", help="run a deterministic fault matrix")
    campaign.add_argument("dataset", type=Path)

    review = commands.add_parser("review", help="human-review workflows")
    review_commands = review.add_subparsers(dest="review_command", required=True)
    template = review_commands.add_parser("template", help="create reviewer JSONL")
    template.add_argument("dataset", type=Path)
    template.add_argument("rubric", type=Path)
    template.add_argument("output", type=Path)
    template.add_argument("--reviewer", required=True)
    analysis = review_commands.add_parser("analyze", help="analyze two reviewers")
    analysis.add_argument("labels", type=Path)
    analysis.add_argument("--report", type=Path)

    return root


def main() -> int:
    args = parser().parse_args()
    if args.command == "run":
        return _run(args)
    if args.command == "replay":
        return _replay(args)
    if args.command == "compare":
        return _compare(args)
    if args.command == "ingest":
        run_id = TraceStore(args.database).ingest(
            load_report(args.report),
            args.traces,
            load_labels(args.labels) if args.labels else None,
        )
        print(f"ingested run_id={run_id}")
        return 0
    if args.command == "query":
        rows = QueryEngine(args.database, args.backend).named(args.name, args.run_id)
        print(json.dumps(rows, indent=2))
        return 0
    if args.command == "campaign":
        report = run_campaign(load_tasks(args.dataset))
        print(
            json.dumps(
                {"cases": len(report.cases), "pass_rate": report.pass_rate}, indent=2
            )
        )
        return 0 if report.pass_rate == 1 else 1
    return _review(args)


def _run(args: argparse.Namespace) -> int:
    runner = EvaluationRunner()
    if args.adapter == "reference":
        report = runner.run(args.dataset, args.evidence_dir)
    else:
        name, version = args.prompt.rsplit("@", 1)
        prompt = PromptRegistry.from_json(args.prompt_registry).get(name, version)
        adapter = (
            ReferenceAdapter()
            if args.adapter == "reference"
            else OpenAIResponsesAdapter(
                model=args.model,
                temperature=args.temperature,
                top_p=args.top_p,
                seed=args.seed,
                max_rounds=args.max_rounds,
                max_retries=args.max_retries,
                input_cost_per_million=args.input_cost_per_million,
                output_cost_per_million=args.output_cost_per_million,
            )
        )
        report = asyncio.run(
            runner.run_adapter(
                args.dataset,
                args.evidence_dir,
                adapter,
                prompt,
                repetitions=args.repetitions,
                concurrency=args.concurrency,
                resume=not args.no_resume,
            )
        )
    print(
        f"actual={report.pass_count}/{report.task_count}; "
        f"expected-outcomes={report.expected_outcomes_matched}/{report.task_count}; "
        f"overall={report.overall:.2f}"
    )
    return 0 if runner.outcomes_match(report) else 1


def _replay(args: argparse.Namespace) -> int:
    trace = read_trace(args.trace)
    tasks = {task.id: task for task in load_tasks(args.dataset)}
    if trace.task_id not in tasks:
        raise SystemExit(f"Task {trace.task_id!r} not found")
    replayed, stable = replay(tasks[trace.task_id], trace)
    print(f"stable={str(stable).lower()} digest={replayed.digest}")
    return 0 if stable else 1


def _compare(args: argparse.Namespace) -> int:
    thresholds = Thresholds(
        max_overall_drop=args.max_overall_drop,
        max_dimension_drop=args.max_dimension_drop,
        allow_new_failures=args.allow_new_failures,
    )
    result = compare(
        load_report(args.baseline), load_report(args.candidate), thresholds
    )
    print(json.dumps(asdict(result), indent=2))
    return 0 if result.passed else 1


def _review(args: argparse.Namespace) -> int:
    if args.review_command == "template":
        task_ids = [task.id for task in load_tasks(args.dataset)]
        write_template(args.output, task_ids, args.reviewer, load_rubric(args.rubric))
        print(f"wrote {len(task_ids)} labels to {args.output}")
        return 0
    labels = load_labels(args.labels)
    agreement = analyze(labels)
    if args.report:
        report = load_report(args.report)
        scorer = {item.task_id: item.passed for item in report.results}
        disagreements = sorted(
            label.task_id
            for label in labels
            if label.task_id in scorer
            and (label.verdict == "pass") != scorer[label.task_id]
        )
        report.human_review = {
            **asdict(agreement),
            "scorer_disagreements": sorted(set(disagreements)),
        }
        from .io import write_json

        write_json(args.report, report.model_dump(mode="json"))
    print(json.dumps(asdict(agreement), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
