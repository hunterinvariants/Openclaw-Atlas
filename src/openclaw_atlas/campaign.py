"""Systematic fault-injection campaigns over task workflows."""
from __future__ import annotations
from dataclasses import dataclass
from .models import FaultKind, FaultSpec, TaskSpec
from .scoring import score
from .simulator import DeterministicAgent
@dataclass(frozen=True)
class CampaignCase:
    task_id:str; step:int; fault:str; status:str; passed:bool; overall:float
@dataclass(frozen=True)
class CampaignReport:
    cases:list[CampaignCase]
    @property
    def pass_rate(self)->float: return round(sum(c.passed for c in self.cases)/len(self.cases),4) if self.cases else 0.0

def run_campaign(tasks:list[TaskSpec],faults:tuple[FaultKind,...]=(FaultKind.timeout,FaultKind.malformed_response,FaultKind.stale_data))->CampaignReport:
    cases=[]; agent=DeterministicAgent()
    for task in tasks:
        for step in range(len(task.workflow)):
            for fault in faults:
                variant=task.model_copy(update={"id":f"{task.id}::{step}::{fault.value}","fault":FaultSpec(step=step,kind=fault,attempts=1),"retry_limit":max(1,task.retry_limit),"max_tool_calls":max(task.max_tool_calls,len(task.workflow)+1)})
                trace=agent.run(variant); result=score(variant,trace)
                cases.append(CampaignCase(task.id,step,fault.value,trace.status,result.passed,result.overall))
    return CampaignReport(cases)
