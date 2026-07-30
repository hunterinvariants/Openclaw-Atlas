"""N-run structural stability for deterministic and stochastic adapters."""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from .models import Trace

STABILITY_METHOD = "structural-v2"
STABILITY_WEIGHTS = {"status": 0.2, "tools": 0.4, "errors": 0.2, "answer": 0.2}


def stability_score(traces: list[Trace]) -> float:
    """Score repeat runs without comparing an adapter to a different agent.

    Tool/error structure dominates the score. Final text is a small exact-match
    component because semantically equivalent stochastic phrasing is expected.
    """
    if not traces:
        raise ValueError("at least one trace is required")
    if len(traces) == 1:
        return 1.0

    reference = traces[0]
    comparisons = [_similarity(reference, candidate) for candidate in traces[1:]]
    return round(sum(comparisons) / len(comparisons), 4)


def _similarity(left: Trace, right: Trace) -> float:
    status = float(left.status == right.status)
    tools = _sequence_ratio(_tools(left), _tools(right))
    errors = _sequence_ratio(_errors(left), _errors(right))
    answer = float(_normalize(left.final_answer) == _normalize(right.final_answer))
    return (
        STABILITY_WEIGHTS["status"] * status
        + STABILITY_WEIGHTS["tools"] * tools
        + STABILITY_WEIGHTS["errors"] * errors
        + STABILITY_WEIGHTS["answer"] * answer
    )


def _tools(trace: Trace) -> list[str]:
    return [event.tool or "" for event in trace.events if event.kind == "tool_call"]


def _errors(trace: Trace) -> list[str]:
    return [event.error for event in trace.events if event.error is not None]


def _sequence_ratio(left: list[str], right: list[str]) -> float:
    if not left and not right:
        return 1.0
    return SequenceMatcher(a=left, b=right, autojunk=False).ratio()


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())
