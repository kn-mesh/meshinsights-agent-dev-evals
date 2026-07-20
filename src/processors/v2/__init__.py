"""Progressive case-brief and capability-driven processors for pipeline v2."""

from src.processors.v2.structured_outputs import V2InvestigationCaseBrief
from src.processors.v2.v2_capability_investigation_ai_agent_processor import (
    V2CapabilityInvestigationAIAgentProcessor,
    V2CapabilityInvestigationAIAgentProcessorConfig,
)
from src.processors.v2.v2_case_brief_ai_workflow_processor import (
    V2CaseBriefAIWorkflowProcessor,
    V2CaseBriefAIWorkflowProcessorConfig,
)

__all__ = [
    "V2CaseBriefAIWorkflowProcessor",
    "V2CaseBriefAIWorkflowProcessorConfig",
    "V2CapabilityInvestigationAIAgentProcessor",
    "V2CapabilityInvestigationAIAgentProcessorConfig",
    "V2InvestigationCaseBrief",
]
