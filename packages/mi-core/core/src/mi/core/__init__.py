"""Mesh Insights Core - runtime primitives and pipeline orchestrators.

Exposes the high-level types used to compose, configure, and execute
pipelines. Import subpackages directly for custom retrievers, processors,
and actions, or use the convenience re-exports here.

Main components: Pipeline, PipelineBuilder, PipelineOrchestrator,
ProcessDataObject, ActionDataObject, RetrieverDataObject,
BaseRetriever, BaseProcessor, BaseAction, BaseHydrator.

See docs/architecture.md for the design overview.
"""
# ruff: noqa: F401, F403

from .objects import *
from .processors import *
from .retrievers import *
from .actions import *
from .hydrators import *
from .registry import *
from .versioning import *

from .pipeline_receipt import PipelineReceipt, StageReceipt
from .pipeline import Pipeline, PipelineConfig, PipelineMetadata
from .pipeline_builder import PipelineBuilder
from .pipeline_orchestrator import PipelineOrchestrator, OrchestratorConfig
from .utils.environment import bootstrap_environment
from .utils.telemetry import bootstrap_telemetry
