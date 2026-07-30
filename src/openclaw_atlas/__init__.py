"""OPENCLAW-ATLAS: evaluation and reliability for tool-using agents."""

from .adapters import (
    AgentAdapter,
    AnthropicMessagesAdapter,
    PromptTemplate,
    ReferenceAdapter,
)
from .models import EvaluationResult, TaskSpec, Trace
from .runner import EvaluationRunner

__all__ = [
    "AgentAdapter",
    "AnthropicMessagesAdapter",
    "EvaluationResult",
    "EvaluationRunner",
    "PromptTemplate",
    "ReferenceAdapter",
    "TaskSpec",
    "Trace",
]
__version__ = "0.6.0"
