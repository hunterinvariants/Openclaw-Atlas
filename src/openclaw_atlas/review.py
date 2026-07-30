"""Rubric-based human review and inter-rater reliability."""
from __future__ import annotations
from dataclasses import dataclass, field
@dataclass(frozen=True)
class Criterion:
    name:str; weight:float; description:str=""
@dataclass(frozen=True)
class Rubric:
    name:str; version:str; criteria:tuple[Criterion,...]
    def __post_init__(self):
        if not self.criteria or any(c.weight<=0 for c in self.criteria): raise ValueError("rubric weights must be positive")
@dataclass(frozen=True)
class Label:
    task_id:str; reviewer:str; verdict:str; notes:str=""; scores:dict[str,float]=field(default_factory=dict); rubric_version:str="1"
    def weighted_score(self,rubric:Rubric)->float:
        missing={c.name for c in rubric.criteria}-self.scores.keys()
        if missing: raise ValueError(f"missing rubric scores: {sorted(missing)}")
        if any(not 0<=self.scores[c.name]<=1 for c in rubric.criteria): raise ValueError("scores must be in [0,1]")
        total=sum(c.weight for c in rubric.criteria)
        return round(sum(self.scores[c.name]*c.weight for c in rubric.criteria)/total,4)
@dataclass(frozen=True)
class Agreement:
    reviewers:list[str]; shared_tasks:int; agreement:float; cohens_kappa:float; disagreements:list[str]
def analyze(labels:list[Label])->Agreement:
    reviewers=sorted({x.reviewer for x in labels})
    if len(reviewers)!=2: raise ValueError("exactly two reviewers required")
    maps={r:{x.task_id:x.verdict for x in labels if x.reviewer==r} for r in reviewers}; tasks=sorted(maps[reviewers[0]].keys() & maps[reviewers[1]].keys())
    if not tasks: raise ValueError("reviewers have no shared tasks")
    pairs=[(maps[reviewers[0]][t],maps[reviewers[1]][t]) for t in tasks]; observed=sum(a==b for a,b in pairs)/len(pairs)
    p1=sum(a=="pass" for a,_ in pairs)/len(pairs); p2=sum(b=="pass" for _,b in pairs)/len(pairs); expected=p1*p2+(1-p1)*(1-p2)
    kappa=1.0 if expected==1 and observed==1 else (observed-expected)/(1-expected)
    return Agreement(reviewers,len(tasks),round(observed,4),round(kappa,4),[t for t,p in zip(tasks,pairs) if p[0]!=p[1]])
