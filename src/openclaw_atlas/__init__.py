"""OPENCLAW-ATLAS: deterministic evaluation for tool-using agents."""

from .models import EvaluationResult, TaskSpec, Trace
from .runner import EvaluationRunner

__all__ = ["EvaluationResult", "EvaluationRunner", "TaskSpec", "Trace"]
__version__ = "0.2.0"

