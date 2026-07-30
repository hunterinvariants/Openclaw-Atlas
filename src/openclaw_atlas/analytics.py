"""Transactional SQLite warehouse for trace-level analysis."""
from __future__ import annotations
import json, sqlite3
from pathlib import Path
from .models import EvaluationReport, Trace
SCHEMA="""
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS runs(id INTEGER PRIMARY KEY, generated_at TEXT, dataset TEXT, overall REAL, pass_count INTEGER, task_count INTEGER);
CREATE TABLE IF NOT EXISTS tasks(run_id INTEGER, task_id TEXT, digest TEXT, overall REAL, passed INTEGER, PRIMARY KEY(run_id,task_id), FOREIGN KEY(run_id) REFERENCES runs(id));
CREATE TABLE IF NOT EXISTS scores(run_id INTEGER, task_id TEXT, dimension TEXT, value REAL, PRIMARY KEY(run_id,task_id,dimension));
CREATE TABLE IF NOT EXISTS events(run_id INTEGER, task_id TEXT, sequence INTEGER, kind TEXT, tool TEXT, error TEXT, attempt INTEGER, payload TEXT, PRIMARY KEY(run_id,task_id,sequence));
CREATE INDEX IF NOT EXISTS idx_events_tool ON events(tool); CREATE INDEX IF NOT EXISTS idx_events_error ON events(error);
"""
class TraceStore:
    def __init__(self,path:Path): self.path=path
    def ingest(self,report:EvaluationReport,traces:Path)->int:
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.executescript(SCHEMA); cur=db.execute("INSERT INTO runs(generated_at,dataset,overall,pass_count,task_count) VALUES(?,?,?,?,?)",(report.generated_at,report.dataset,report.overall,report.pass_count,report.task_count)); run=int(cur.lastrowid)
            for r in report.results:
                db.execute("INSERT INTO tasks VALUES(?,?,?,?,?)",(run,r.task_id,r.trace_digest,r.overall,int(r.passed)))
                db.executemany("INSERT INTO scores VALUES(?,?,?,?)",[(run,r.task_id,k,v.value) for k,v in r.scores.items()])
                trace=Trace.model_validate_json((traces/f"{r.task_id}.json").read_text(encoding="utf-8"))
                db.executemany("INSERT INTO events VALUES(?,?,?,?,?,?,?,?)",[(run,r.task_id,e.sequence,e.kind,e.tool,e.error,e.attempt,json.dumps(e.result,sort_keys=True)) for e in trace.events])
            return run
    def summary(self,run_id:int|None=None)->dict:
        with sqlite3.connect(self.path) as db:
            db.row_factory=sqlite3.Row
            run_id=run_id or db.execute("SELECT max(id) FROM runs").fetchone()[0]
            run=db.execute("SELECT * FROM runs WHERE id=?",(run_id,)).fetchone()
            if not run: raise ValueError(f"run {run_id} not found")
            errors=db.execute("SELECT error,count(*) count FROM events WHERE run_id=? AND error IS NOT NULL GROUP BY error ORDER BY error",(run_id,)).fetchall()
            tools=db.execute("SELECT tool,count(*) calls FROM events WHERE run_id=? AND kind='tool_call' GROUP BY tool ORDER BY calls DESC,tool",(run_id,)).fetchall()
            return {"run":dict(run),"errors":[dict(x) for x in errors],"tools":[dict(x) for x in tools]}
