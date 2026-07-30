"""Transactional SQLite warehouse for trace-level analysis."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .models import EvaluationReport, EvaluationResult, Trace
from .review import Label

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS runs(
  id INTEGER PRIMARY KEY, generated_at TEXT, dataset TEXT, overall REAL,
  pass_count INTEGER, task_count INTEGER
);
CREATE TABLE IF NOT EXISTS tasks(
  run_id INTEGER, task_id TEXT, digest TEXT, overall REAL, passed INTEGER,
  PRIMARY KEY(run_id,task_id), FOREIGN KEY(run_id) REFERENCES runs(id)
);
CREATE TABLE IF NOT EXISTS scores(
  run_id INTEGER, task_id TEXT, dimension TEXT, value REAL,
  PRIMARY KEY(run_id,task_id,dimension)
);
CREATE TABLE IF NOT EXISTS events(
  run_id INTEGER, task_id TEXT, sequence INTEGER, kind TEXT, tool TEXT,
  error TEXT, attempt INTEGER, payload TEXT,
  PRIMARY KEY(run_id,task_id,sequence)
);
CREATE INDEX IF NOT EXISTS idx_events_tool ON events(tool);
CREATE INDEX IF NOT EXISTS idx_events_error ON events(error);
CREATE TABLE IF NOT EXISTS reviews(
  run_id INTEGER, task_id TEXT, reviewer TEXT, verdict TEXT, notes TEXT,
  scores TEXT, PRIMARY KEY(run_id,task_id,reviewer)
);
"""


class TraceStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def ingest(
        self, report: EvaluationReport, traces: Path, labels: list[Label] | None = None
    ) -> int:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as database:
            database.executescript(SCHEMA)
            cursor = database.execute(
                "INSERT INTO runs(generated_at,dataset,overall,pass_count,task_count) "
                "VALUES(?,?,?,?,?)",
                (
                    report.generated_at,
                    report.dataset,
                    report.overall,
                    report.pass_count,
                    report.task_count,
                ),
            )
            if cursor.lastrowid is None:
                raise RuntimeError("SQLite did not return a run ID")
            run_id = cursor.lastrowid
            for result in report.results:
                self._ingest_result(database, run_id, result, traces)
            if labels:
                database.executemany(
                    "INSERT INTO reviews VALUES(?,?,?,?,?,?)",
                    [
                        (
                            run_id,
                            item.task_id,
                            item.reviewer,
                            item.verdict,
                            item.notes,
                            json.dumps(item.scores, sort_keys=True),
                        )
                        for item in labels
                    ],
                )
            return run_id

    @staticmethod
    def _ingest_result(
        database: sqlite3.Connection,
        run_id: int,
        result: EvaluationResult,
        traces: Path,
    ) -> None:
        database.execute(
            "INSERT INTO tasks VALUES(?,?,?,?,?)",
            (
                run_id,
                result.task_id,
                result.trace_digest,
                result.overall,
                int(result.passed),
            ),
        )
        database.executemany(
            "INSERT INTO scores VALUES(?,?,?,?)",
            [
                (run_id, result.task_id, name, value.value)
                for name, value in result.scores.items()
            ],
        )
        trace = Trace.model_validate_json(
            (traces / f"{result.task_id}.json").read_text(encoding="utf-8")
        )
        database.executemany(
            "INSERT INTO events VALUES(?,?,?,?,?,?,?,?)",
            [
                (
                    run_id,
                    result.task_id,
                    event.sequence,
                    event.kind,
                    event.tool,
                    event.error,
                    event.attempt,
                    json.dumps(event.result, sort_keys=True),
                )
                for event in trace.events
            ],
        )

    def summary(self, run_id: int | None = None) -> dict[str, Any]:
        with sqlite3.connect(self.path) as database:
            database.row_factory = sqlite3.Row
            selected = (
                run_id or database.execute("SELECT max(id) FROM runs").fetchone()[0]
            )
            run = database.execute(
                "SELECT * FROM runs WHERE id=?", (selected,)
            ).fetchone()
            if not run:
                raise ValueError(f"run {selected} not found")
            errors = database.execute(
                "SELECT error,count(*) count FROM events "
                "WHERE run_id=? AND error IS NOT NULL "
                "GROUP BY error ORDER BY error",
                (selected,),
            ).fetchall()
            tools = database.execute(
                "SELECT tool,count(*) calls FROM events "
                "WHERE run_id=? AND kind='tool_call' "
                "GROUP BY tool ORDER BY calls DESC,tool",
                (selected,),
            ).fetchall()
            return {
                "run": dict(run),
                "errors": [dict(row) for row in errors],
                "tools": [dict(row) for row in tools],
            }
