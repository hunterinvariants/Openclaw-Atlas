import asyncio, json, sys
from pathlib import Path
import pytest
from openclaw_atlas.adapters import CallableAdapter, PromptRegistry, PromptTemplate, ReferenceAdapter
from openclaw_atlas.analytics import TraceStore
from openclaw_atlas.cli import main
from openclaw_atlas.io import load_tasks
from openclaw_atlas.query import QueryEngine
from openclaw_atlas.review import Criterion, Label, Rubric
from openclaw_atlas.runner import EvaluationRunner

DATASET=Path("datasets/milestone-1.jsonl")
def invoke(monkeypatch,args): monkeypatch.setattr(sys,"argv",["atlas",*args]); return main()

def test_prompt_registry_adapter_and_provenance(tmp_path):
 registry=PromptRegistry.from_json(Path("prompts.json")); prompt=registry.get("tool-agent","2"); assert prompt.digest==prompt.digest and "Plan briefly" in prompt.render(load_tasks(DATASET)[0])
 with pytest.raises(KeyError): registry.get("missing","1")
 with pytest.raises(ValueError): PromptRegistry([prompt,prompt])
 evidence=tmp_path/"adapter"; report=asyncio.run(EvaluationRunner().run_adapter(DATASET,evidence,ReferenceAdapter(),prompt)); assert report.pass_count==20
 provenance=json.loads((evidence/"provenance.json").read_text()); assert provenance["adapter"]=="deterministic-reference" and len(provenance["prompt_digest"])==64


def test_callable_adapter_validates_task_identity():
 task=load_tasks(DATASET)[0]; prompt=PromptTemplate("x","1","{prompt}")
 async def good(t,p): return await ReferenceAdapter().run(t,prompt)
 assert asyncio.run(CallableAdapter("custom",good).run(task,prompt)).task_id==task.id
 async def bad(t,p):
  trace=await ReferenceAdapter().run(t,prompt); return trace.model_copy(update={"task_id":"wrong"})
 with pytest.raises(ValueError): asyncio.run(CallableAdapter("bad",bad).run(task,prompt))


def test_weighted_rubric_validation():
 rubric=Rubric("agent-qa","1",(Criterion("grounding",2),Criterion("safety",1)))
 label=Label("t","alice","pass",scores={"grounding":1,"safety":.5}); assert label.weighted_score(rubric)==.8333
 with pytest.raises(ValueError): Label("t","a","fail",scores={}).weighted_score(rubric)
 with pytest.raises(ValueError): Label("t","a","fail",scores={"grounding":2,"safety":1}).weighted_score(rubric)
 with pytest.raises(ValueError): Rubric("bad","1",())


def test_query_catalog_and_read_only_guard(tmp_path):
 evidence=tmp_path/"e"; report=EvaluationRunner().run(DATASET,evidence); db=tmp_path/"atlas.db"; run=TraceStore(db).ingest(report,evidence/"traces"); engine=QueryEngine(db)
 rows=engine.named("dimension_scores",run); assert len(rows)==5 and all(r["average"]==1 for r in rows)
 assert engine.named("tool_errors",run)
 with pytest.raises(ValueError): engine.execute("DELETE FROM runs")
 with pytest.raises(ValueError): engine.execute("SELECT 1; DELETE FROM runs")
 with pytest.raises(KeyError): engine.named("missing",run)
 with pytest.raises(ValueError): QueryEngine(db,"other")


def test_all_cli_workflows(monkeypatch,tmp_path,capsys):
 evidence=tmp_path/"e"
 assert invoke(monkeypatch,["run",str(DATASET),"--evidence-dir",str(evidence),"--prompt-registry","prompts.json"])==0
 assert invoke(monkeypatch,["replay",str(DATASET),str(evidence/"traces/timeout-recovery.json")])==0
 assert invoke(monkeypatch,["compare",str(evidence/"report.json"),str(evidence/"report.json")])==0
 db=tmp_path/"cli.db"; assert invoke(monkeypatch,["ingest",str(evidence/"report.json"),str(evidence/"traces"),str(db)])==0
 assert invoke(monkeypatch,["query",str(db),"dimension_scores"])==0
 assert invoke(monkeypatch,["campaign",str(DATASET)])==0
 assert "pass_rate" in capsys.readouterr().out
