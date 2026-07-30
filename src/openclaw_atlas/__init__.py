"""OPENCLAW-ATLAS: evaluation and reliability for tool-using agents."""

from .adapters import (
    AgentAdapter,
    OpenAIResponsesAdapter,
    PromptTemplate,
    ReferenceAdapter,
)
from .models import EvaluationResult, TaskSpec, Trace
from .runner import EvaluationRunner

__all__ = [
    "AgentAdapter",
    "EvaluationResult",
    "EvaluationRunner",
    "OpenAIResponsesAdapter",
    "PromptTemplate",
    "ReferenceAdapter",
    "TaskSpec",
    "Trace",
]
__version__ = "0.6.0"
