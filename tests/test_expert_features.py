from pathlib import Path
from openclaw_atlas.analytics import TraceStore
from openclaw_atlas.campaign import run_campaign
from openclaw_atlas.io import load_tasks
from openclaw_atlas.models import DimensionScore, EvaluationReport, EvaluationResult, Trace, TraceEvent
from openclaw_atlas.policy import Policy, evaluate
from openclaw_atlas.regression import Thresholds, compare
from openclaw_atlas.review import Label, analyze
from openclaw_atlas.runner import EvaluationRunner

DATASET=Path("datasets/milestone-1.jsonl")
def report(score:float,passed:bool=True)->EvaluationReport:
    result=EvaluationResult(task_id="t",trace_digest="x",scores={k:DimensionScore(value=score,reason="test") for k in ("correctness","safety","efficiency","robustness","reproducibility")},overall=score,passed=passed)
    return EvaluationReport.create("test",[result])

def test_regression_gate_detects_score_drop():
    result=compare(report(1.0),report(0.7,False),Thresholds())
    assert not result.passed and result.new_failures==["t"]
    assert "overall_drop:-0.3000" in result.violations

def test_trace_store_normalizes_report(tmp_path:Path):
    evidence=tmp_path/"evidence"; generated=EvaluationRunner().run(DATASET,evidence)
    store=TraceStore(tmp_path/"atlas.db"); run_id=store.ingest(generated,evidence/"traces"); summary=store.summary(run_id)
    assert summary["run"]["task_count"]==20
    assert {x["error"] for x in summary["errors"]}=={"malformed_response","permission_denied","stale_data","timeout"}

def test_policy_finds_forbidden_tool_and_secret():
    trace=Trace(task_id="x",events=[TraceEvent(sequence=0,kind="tool_call",tool="admin.delete",arguments={"token":"x"})],final_answer="",status="completed")
    assert evaluate(trace,Policy(frozenset({"admin.delete"})))==["forbidden_tool_called","sensitive_argument_exposed"]

def test_review_agreement_reports_kappa_and_disagreement():
    labels=[Label("a","r1","pass"),Label("b","r1","pass"),Label("c","r1","fail"),Label("a","r2","pass"),Label("b","r2","fail"),Label("c","r2","fail")]
    result=analyze(labels)
    assert result.agreement==0.6667 and result.disagreements==["b"]

def test_fault_campaign_is_deterministic_and_recovers():
    campaign=run_campaign(load_tasks(DATASET)[:2])
    assert len(campaign.cases)==6
    assert campaign.pass_rate==1.0
