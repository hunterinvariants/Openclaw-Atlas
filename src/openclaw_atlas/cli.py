from __future__ import annotations

import argparse
from pathlib import Path

from .io import load_tasks, read_trace
from .replay import replay
from .runner import EvaluationRunner


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="atlas")
    subcommands = result.add_subparsers(dest="command", required=True)
    run = subcommands.add_parser("run", help="Run a deterministic evaluation suite")
    run.add_argument("dataset", type=Path)
    run.add_argument("--evidence-dir", type=Path, default=Path("evidence/latest"))
    replay_command = subcommands.add_parser("replay", help="Replay and verify a saved trace")
    replay_command.add_argument("dataset", type=Path)
    replay_command.add_argument("trace", type=Path)
    return result


def main() -> int:
    args = parser().parse_args()
    if args.command == "run":
        report = EvaluationRunner().run(args.dataset, args.evidence_dir)
        print(f"{report.pass_count}/{report.task_count} passed; overall={report.overall:.2f}")
        return 0 if report.pass_count == report.task_count else 1
    trace = read_trace(args.trace)
    tasks = {task.id: task for task in load_tasks(args.dataset)}
    if trace.task_id not in tasks:
        raise SystemExit(f"Task {trace.task_id!r} not found")
    replayed, stable = replay(tasks[trace.task_id], trace)
    print(f"stable={str(stable).lower()} digest={replayed.digest}")
    return 0 if stable else 1


if __name__ == "__main__":
    raise SystemExit(main())

