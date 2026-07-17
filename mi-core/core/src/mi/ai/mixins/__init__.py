"""AI processor mixins for pipeline integration.

Provides AIWorkflowMixin for single-call structured output and
AIAgentMixin for multi-turn tool-using agent patterns.

See docs/ai.md for usage examples and configuration.
"""
# ruff: noqa: F401

from mi.ai.mixins.base import AIProcessorMixin
from mi.ai.mixins.workflow import AIWorkflowMixin
from mi.ai.mixins.agent import AIAgentMixin, AgentDeps
from mi.ai.model_config import ModelName
from mi.ai.tools import Tool, ToolLike

__all__ = [
    # Base
    "AIProcessorMixin",
    "ModelName",
    # Mixins
    "AIWorkflowMixin",
    "AIAgentMixin",
    # Agent types
    "AgentDeps",
    "ToolLike",
    "Tool",
]
