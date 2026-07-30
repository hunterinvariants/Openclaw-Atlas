"""Deterministic regression gates for evaluation reports."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .models import EvaluationReport


@dataclass(frozen=True)
class Thresholds:
    max_overall_drop: float = 0.02
    max_dimension_drop: float = 0.05
    allow_new_failures: int = 0


@dataclass(frozen=True)
class RegressionResult:
    passed: bool
    overall_delta: float
    dimension_deltas: dict[str, float]
    new_failures: list[str]
    recovered: list[str]
    outcome_mismatches: list[str]
    violations: list[str]


def compare(
    baseline: EvaluationReport,
    candidate: EvaluationReport,
    thresholds: Thresholds | None = None,
) -> RegressionResult:
    limits = thresholds or Thresholds()
    before = {result.task_id: result for result in baseline.results}
    after = {result.task_id: result for result in candidate.results}
    shared = sorted(before.keys() & after.keys())
    if not shared:
        raise ValueError("reports have no shared task IDs")

    overall = round(candidate.overall - baseline.overall, 4)
    dimensions = sorted(baseline.dimensions.keys() & candidate.dimensions.keys())
    deltas = {
        name: round(candidate.dimensions[name] - baseline.dimensions[name], 4)
        for name in dimensions
    }
    new_failures = [
        task_id
        for task_id in shared
        if before[task_id].passed and not after[task_id].passed
    ]
    recovered = [
        task_id
        for task_id in shared
        if not before[task_id].passed and after[task_id].passed
    ]
    outcome_mismatches = [
        task_id for task_id in shared if not after[task_id].outcome_matched
    ]

    violations: list[str] = []
    if overall < -limits.max_overall_drop:
        violations.append(f"overall_drop:{overall:.4f}")
    violations.extend(
        f"dimension_drop:{name}:{delta:.4f}"
        for name, delta in deltas.items()
        if delta < -limits.max_dimension_drop
    )
    if len(new_failures) > limits.allow_new_failures:
        violations.append(f"new_failures:{len(new_failures)}")
    if outcome_mismatches:
        violations.append(f"outcome_mismatches:{len(outcome_mismatches)}")

    return RegressionResult(
        passed=not violations,
        overall_delta=overall,
        dimension_deltas=deltas,
        new_failures=new_failures,
        recovered=recovered,
        outcome_mismatches=outcome_mismatches,
        violations=violations,
    )


def load(path: Path) -> EvaluationReport:
    return EvaluationReport.model_validate_json(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = compare(load(args.baseline), load(args.candidate))
    payload = json.dumps(asdict(result), indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
