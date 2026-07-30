"""Re-check harness fixes against already-paid-for traces. Makes no API calls.

Answers three questions using recorded real-model output:

1. Does the fixed step matcher still reject the tool order the model actually used?
2. Would the answer oracle accept those same values in the format tool-agent@3 asks for?
3. Which dimensions were the harness's fault versus the model's?
"""

from __future__ import annotations

import argparse
from pathlib import Path

from openclaw_atlas.adapters import _find_step
from openclaw_atlas.io import load_tasks, read_trace
from openclaw_atlas.models import Trace
from openclaw_atlas.scoring import score


def evidence_line(trace: Trace) -> str:
    """Rebuild what tool-agent@3 asks for from the results the model actually saw."""
    pairs: list[str] = []
    for event in trace.events:
        if event.kind == "tool_result" and isinstance(event.result, dict):
            pairs += [f"{k}={v}" for k, v in sorted(event.result.items())]
    return "EVIDENCE: " + ", ".join(dict.fromkeys(pairs))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("evidence_dir", type=Path)
    args = parser.parse_args()

    tasks = {task.id: task for task in load_tasks(args.dataset)}
    traces = sorted((args.evidence_dir / "traces").glob("*.json"))
    if not traces:
        print(f"no traces under {args.evidence_dir / 'traces'}")
        return 1

    order_ok = oracle_before = oracle_after = 0
    for path in traces:
        trace = read_trace(path)
        task = tasks.get(trace.task_id)
        if task is None:
            continue

        print(f"\n=== {trace.task_id}")

        # 1. Replay the recorded call order through the fixed matcher.
        called = [e.tool for e in trace.events if e.kind == "tool_call" and e.tool]
        consumed: set[int] = set()
        rejected = []
        for tool in called:
            try:
                consumed.add(_find_step(task, tool, consumed))
            except ValueError:
                rejected.append(tool)
        if rejected:
            print(f"  step matching : REJECTS {rejected}")
        else:
            order_ok += 1
            print(f"  step matching : accepts the model's order {called}")

        # 2. Re-score the real answer, then the same values in the @3 format.
        before = score(task, trace)
        after = score(
            task,
            trace.model_copy(
                update={"final_answer": f"{trace.final_answer}\n{evidence_line(trace)}"}
            ),
        )
        b = before.scores["correctness"].value
        a = after.scores["correctness"].value
        oracle_before += b == 1.0
        oracle_after += a == 1.0
        print(f"  correctness   : {b:.2f} as written -> {a:.2f} in @3 format")
        print(
            f"  overall       : {before.overall:.2f} -> {after.overall:.2f} "
            f"({'PASS' if after.passed else 'FAIL'}, "
            f"expected {'PASS' if task.expected_pass else 'FAIL'})"
        )
        if after.passed != task.expected_pass:
            reasons = [k for k, v in after.scores.items() if v.value < 1.0]
            print(f"  still off     : {reasons or 'call budget'}")

    total = len(traces)
    print(
        f"\nsummary: order accepted {order_ok}/{total} | "
        f"correctness 1.0 in {oracle_before}/{total} as written, "
        f"{oracle_after}/{total} reformatted"
    )
    print(
        "\nThis proves the harness accepts correct work. It does NOT prove the model\n"
        "will follow the @3 format contract - only a real call can show that."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
