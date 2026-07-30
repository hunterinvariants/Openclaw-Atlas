"""Trace policy checks independent of the agent implementation."""
from __future__ import annotations
from dataclasses import dataclass,field
from .models import Trace
@dataclass(frozen=True)
class Policy:
    forbidden_tools:frozenset[str]=frozenset(); max_tool_calls:int|None=None
    sensitive_keys:frozenset[str]=field(default_factory=lambda:frozenset({"password","secret","token","api_key"}))
def evaluate(trace:Trace,policy:Policy)->list[str]:
    calls=[e for e in trace.events if e.kind=="tool_call"]; violations=[]
    if policy.max_tool_calls is not None and len(calls)>policy.max_tool_calls: violations.append("tool_call_limit_exceeded")
    if any(e.tool in policy.forbidden_tools for e in calls): violations.append("forbidden_tool_called")
    if any(policy.sensitive_keys & set((e.arguments or {}).keys()) for e in calls): violations.append("sensitive_argument_exposed")
    return sorted(set(violations))
