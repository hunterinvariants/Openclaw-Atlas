"""Rubric-based human review and inter-rater reliability."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class Criterion:
    name: str
    weight: float
    description: str = ""


@dataclass(frozen=True)
class Rubric:
    name: str
    version: str
    criteria: tuple[Criterion, ...]

    def __post_init__(self) -> None:
        if not self.criteria or any(item.weight <= 0 for item in self.criteria):
            raise ValueError("rubric weights must be positive")


@dataclass(frozen=True)
class Label:
    task_id: str
    reviewer: str
    verdict: Literal["pass", "fail", "unreviewed"]
    notes: str = ""
    scores: dict[str, float] = field(default_factory=dict)
    rubric_version: str = "1"

    def __post_init__(self) -> None:
        if not self.reviewer.strip():
            raise ValueError("reviewer is required")
        if self.verdict not in {"pass", "fail", "unreviewed"}:
            raise ValueError("verdict must be pass, fail or unreviewed")

    def weighted_score(self, rubric: Rubric) -> float:
        missing = {item.name for item in rubric.criteria} - self.scores.keys()
        if missing:
            raise ValueError(f"missing rubric scores: {sorted(missing)}")
        if any(not 0 <= self.scores[item.name] <= 1 for item in rubric.criteria):
            raise ValueError("scores must be in [0,1]")
        total = sum(item.weight for item in rubric.criteria)
        weighted = sum(self.scores[item.name] * item.weight for item in rubric.criteria)
        return round(weighted / total, 4)


@dataclass(frozen=True)
class Agreement:
    reviewers: list[str]
    shared_tasks: int
    agreement: float
    cohens_kappa: float
    disagreements: list[str]


def analyze(labels: list[Label]) -> Agreement:
    pending = sorted(
        {label.task_id for label in labels if label.verdict == "unreviewed"}
    )
    if pending:
        raise ValueError(
            f"{len(pending)} label(s) still unreviewed: {', '.join(pending[:5])}"
        )
    reviewers = sorted({label.reviewer for label in labels})
    if len(reviewers) != 2:
        raise ValueError("exactly two reviewers required")
    mappings = {
        reviewer: {
            label.task_id: label.verdict
            for label in labels
            if label.reviewer == reviewer
        }
        for reviewer in reviewers
    }
    tasks = sorted(set(mappings[reviewers[0]]) & set(mappings[reviewers[1]]))
    if not tasks:
        raise ValueError("reviewers have no shared tasks")
    pairs = [
        (mappings[reviewers[0]][task], mappings[reviewers[1]][task]) for task in tasks
    ]
    observed = sum(left == right for left, right in pairs) / len(pairs)
    left_pass = sum(left == "pass" for left, _ in pairs) / len(pairs)
    right_pass = sum(right == "pass" for _, right in pairs) / len(pairs)
    expected = left_pass * right_pass + (1 - left_pass) * (1 - right_pass)
    kappa = (
        1.0
        if expected == 1 and observed == 1
        else (observed - expected) / (1 - expected)
    )
    return Agreement(
        reviewers=reviewers,
        shared_tasks=len(tasks),
        agreement=round(observed, 4),
        cohens_kappa=round(kappa, 4),
        disagreements=[
            task for task, pair in zip(tasks, pairs, strict=True) if pair[0] != pair[1]
        ],
    )


def load_labels(path: Path) -> list[Label]:
    labels: list[Label] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8-sig").splitlines(), 1
    ):
        if not line.strip():
            continue
        try:
            labels.append(Label(**json.loads(line)))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"{path}:{line_number}: invalid review label") from exc
    return labels


def load_rubric(path: Path) -> Rubric:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    criteria = tuple(Criterion(**item) for item in payload.pop("criteria"))
    return Rubric(criteria=criteria, **payload)


def write_template(
    path: Path, task_ids: list[str], reviewer: str, rubric: Rubric
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Deliberately unscored: a half-finished template must never read as a
    # set of passing verdicts.
    scores: dict[str, float] = {}
    rows = [
        json.dumps(
            asdict(
                Label(
                    task_id=task_id,
                    reviewer=reviewer,
                    verdict="unreviewed",
                    scores=scores,
                    rubric_version=rubric.version,
                )
            ),
            sort_keys=True,
        )
        for task_id in task_ids
    ]
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
