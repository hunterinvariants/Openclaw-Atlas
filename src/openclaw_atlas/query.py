"""Read-only trace query layer with SQLite and optional DuckDB backends."""
from __future__ import annotations
from pathlib import Path
import re, sqlite3
READ_ONLY=re.compile(r"^\s*(select|with)\b",re.I)
CATALOG={
 "failures":"SELECT task_id, overall FROM tasks WHERE run_id = ? AND passed = 0 ORDER BY overall",
 "tool_errors":"SELECT tool, error, count(*) AS occurrences FROM events WHERE run_id = ? AND error IS NOT NULL GROUP BY tool,error ORDER BY occurrences DESC",
 "dimension_scores":"SELECT dimension, avg(value) AS average FROM scores WHERE run_id = ? GROUP BY dimension ORDER BY dimension",
 "expensive_tasks":"SELECT task_id, count(*) AS calls FROM events WHERE run_id = ? AND kind = 'tool_call' GROUP BY task_id ORDER BY calls DESC,task_id",
}
class QueryEngine:
    def __init__(self,path:Path,backend:str="sqlite"):
        if backend not in {"sqlite","duckdb"}: raise ValueError("backend must be sqlite or duckdb")
        self.path,self.backend=path,backend
    def _connect(self):
        if self.backend=="sqlite": return sqlite3.connect(self.path)
        try: import duckdb
        except ImportError as exc: raise RuntimeError("install openclaw-atlas[duckdb]") from exc
        return duckdb.connect(str(self.path),read_only=True)
    def execute(self,sql:str,params:tuple=())->list[dict]:
        if not READ_ONLY.match(sql) or ";" in sql.rstrip().rstrip(";"): raise ValueError("only one read-only SELECT/CTE is allowed")
        with self._connect() as db:
            cursor=db.execute(sql,params); names=[x[0] for x in cursor.description]
            return [dict(zip(names,row)) for row in cursor.fetchall()]
    def named(self,name:str,run_id:int)->list[dict]:
        if name not in CATALOG: raise KeyError(f"unknown query {name}")
        return self.execute(CATALOG[name],(run_id,))
