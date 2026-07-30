from __future__ import annotations
from hashlib import sha256
from pathlib import Path
from .adapters import AgentAdapter, PromptTemplate
from .io import load_tasks, write_json, write_trace
from .models import EvaluationReport
from .scoring import score
from .simulator import DeterministicAgent

class EvaluationRunner:
    def run(self,dataset:Path,evidence_dir:Path)->EvaluationReport:
        tasks=load_tasks(dataset); results=[]
        for task in tasks:
            trace=DeterministicAgent().run(task); write_trace(evidence_dir/"traces"/f"{task.id}.json",trace); results.append(score(task,trace))
        report=EvaluationReport.create(str(dataset.as_posix()),results); self._write(evidence_dir,report); return report
    async def run_adapter(self,dataset:Path,evidence_dir:Path,adapter:AgentAdapter,prompt:PromptTemplate)->EvaluationReport:
        tasks=load_tasks(dataset); results=[]
        for task in tasks:
            trace=await adapter.run(task,prompt); write_trace(evidence_dir/"traces"/f"{task.id}.json",trace); results.append(score(task,trace))
        report=EvaluationReport.create(str(dataset.as_posix()),results); self._write(evidence_dir,report)
        write_json(evidence_dir/"provenance.json",{"adapter":adapter.adapter_id,"prompt":f"{prompt.name}@{prompt.version}","prompt_digest":prompt.digest,"dataset_digest":sha256(dataset.read_bytes()).hexdigest()})
        return report
    def _write(self,evidence_dir:Path,report:EvaluationReport)->None:
        write_json(evidence_dir/"report.json",report.model_dump(mode="json")); (evidence_dir/"report.md").write_text(self.to_markdown(report),encoding="utf-8")
    @staticmethod
    def to_markdown(report:EvaluationReport)->str:
        rows="\n".join(f"| {r.task_id} | {r.overall:.2f} | {'PASS' if r.passed else 'FAIL'} |" for r in report.results); dimensions="\n".join(f"- {n}: {v:.2f}" for n,v in report.dimensions.items())
        return f"# OPENCLAW-ATLAS Evaluation Report\n\n- Dataset: `{report.dataset}`\n- Tasks: {report.task_count}\n- Passed: {report.pass_count}\n- Overall: {report.overall:.2f}\n\n## Dimension averages\n\n{dimensions}\n\n## Results\n\n| Task | Overall | Status |\n|---|---:|---|\n{rows}\n"
