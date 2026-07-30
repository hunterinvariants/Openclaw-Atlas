from __future__ import annotations
import argparse, asyncio, json
from dataclasses import asdict
from pathlib import Path
from .adapters import PromptRegistry, ReferenceAdapter
from .analytics import TraceStore
from .campaign import run_campaign
from .io import load_tasks, read_trace
from .query import CATALOG, QueryEngine
from .regression import Thresholds, compare, load as load_report
from .replay import replay
from .runner import EvaluationRunner

def parser()->argparse.ArgumentParser:
 p=argparse.ArgumentParser(prog="atlas"); sub=p.add_subparsers(dest="command",required=True)
 run=sub.add_parser("run",help="run an evaluation suite"); run.add_argument("dataset",type=Path);run.add_argument("--evidence-dir",type=Path,default=Path("evidence/latest"));run.add_argument("--prompt-registry",type=Path);run.add_argument("--prompt",default="tool-agent@2")
 r=sub.add_parser("replay");r.add_argument("dataset",type=Path);r.add_argument("trace",type=Path)
 c=sub.add_parser("compare");c.add_argument("baseline",type=Path);c.add_argument("candidate",type=Path);c.add_argument("--max-overall-drop",type=float,default=.02);c.add_argument("--max-dimension-drop",type=float,default=.05);c.add_argument("--allow-new-failures",type=int,default=0)
 i=sub.add_parser("ingest");i.add_argument("report",type=Path);i.add_argument("traces",type=Path);i.add_argument("database",type=Path)
 q=sub.add_parser("query");q.add_argument("database",type=Path);q.add_argument("name",choices=sorted(CATALOG));q.add_argument("--run-id",type=int,default=1);q.add_argument("--backend",choices=["sqlite","duckdb"],default="sqlite")
 f=sub.add_parser("campaign");f.add_argument("dataset",type=Path)
 return p

def main()->int:
 a=parser().parse_args()
 if a.command=="run":
  runner=EvaluationRunner()
  if a.prompt_registry:
   name,version=a.prompt.rsplit("@",1);prompt=PromptRegistry.from_json(a.prompt_registry).get(name,version);report=asyncio.run(runner.run_adapter(a.dataset,a.evidence_dir,ReferenceAdapter(),prompt))
  else: report=runner.run(a.dataset,a.evidence_dir)
  print(f"{report.pass_count}/{report.task_count} passed; overall={report.overall:.2f}");return 0 if report.pass_count==report.task_count else 1
 if a.command=="replay":
  trace=read_trace(a.trace);tasks={t.id:t for t in load_tasks(a.dataset)}
  if trace.task_id not in tasks: raise SystemExit(f"Task {trace.task_id!r} not found")
  again,stable=replay(tasks[trace.task_id],trace);print(f"stable={str(stable).lower()} digest={again.digest}");return 0 if stable else 1
 if a.command=="compare":
  result=compare(load_report(a.baseline),load_report(a.candidate),Thresholds(a.max_overall_drop,a.max_dimension_drop,a.allow_new_failures));print(json.dumps(asdict(result),indent=2));return 0 if result.passed else 1
 if a.command=="ingest":
  run=TraceStore(a.database).ingest(load_report(a.report),a.traces);print(f"ingested run_id={run}");return 0
 if a.command=="query": print(json.dumps(QueryEngine(a.database,a.backend).named(a.name,a.run_id),indent=2));return 0
 campaign=run_campaign(load_tasks(a.dataset));print(json.dumps({"cases":len(campaign.cases),"pass_rate":campaign.pass_rate},indent=2));return 0 if campaign.pass_rate==1 else 1
if __name__=="__main__":raise SystemExit(main())
