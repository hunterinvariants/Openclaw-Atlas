"""Deterministic regression gates for evaluation reports."""
from __future__ import annotations
import argparse, json
from dataclasses import dataclass, asdict
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
    violations: list[str]

def compare(baseline: EvaluationReport, candidate: EvaluationReport, thresholds: Thresholds = Thresholds()) -> RegressionResult:
    before = {r.task_id: r for r in baseline.results}; after = {r.task_id: r for r in candidate.results}
    shared = sorted(before.keys() & after.keys())
    if not shared: raise ValueError("reports have no shared task IDs")
    overall = round(candidate.overall - baseline.overall, 4)
    deltas = {k: round(candidate.dimensions[k] - baseline.dimensions[k], 4) for k in sorted(baseline.dimensions.keys() & candidate.dimensions.keys())}
    new = [k for k in shared if before[k].passed and not after[k].passed]
    recovered = [k for k in shared if not before[k].passed and after[k].passed]
    violations = []
    if overall < -thresholds.max_overall_drop: violations.append(f"overall_drop:{overall:.4f}")
    violations += [f"dimension_drop:{k}:{v:.4f}" for k,v in deltas.items() if v < -thresholds.max_dimension_drop]
    if len(new) > thresholds.allow_new_failures: violations.append(f"new_failures:{len(new)}")
    return RegressionResult(not violations, overall, deltas, new, recovered, violations)

def load(path: Path) -> EvaluationReport: return EvaluationReport.model_validate_json(path.read_text(encoding="utf-8"))
def main() -> int:
    p=argparse.ArgumentParser(); p.add_argument("baseline",type=Path); p.add_argument("candidate",type=Path); p.add_argument("--output",type=Path); a=p.parse_args()
    result=compare(load(a.baseline),load(a.candidate)); payload=json.dumps(asdict(result),indent=2,sort_keys=True)
    if a.output: a.output.write_text(payload+"\n",encoding="utf-8")
    print(payload); return 0 if result.passed else 1
if __name__ == "__main__": raise SystemExit(main())
