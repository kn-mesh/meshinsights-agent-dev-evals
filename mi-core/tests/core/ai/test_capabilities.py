"""Tests for backend-neutral capabilities, toolsets, and Agent Skills."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel
import pytest

from mi.ai import (
    AIAgentMixin,
    AICapability,
    AIProcessorConfig,
    AISkill,
    ToolSet,
    UserMessage,
    ai_tool,
    load_skills,
)
from mi.ai.backends.base import AIUsage, AgentRequest, AgentResult
from mi.ai.capabilities import normalize_capabilities
from mi.core import BaseProcessor, ProcessDataObject


class ExampleOutput(BaseModel):
    """Structured result used by capability-only agent tests."""

    value: int


def example_tool() -> str:
    """Return a deterministic example result."""
    return "done"


def test_toolset_builder_preserves_shared_behavior() -> None:
    """Build reusable toolsets with instructions and deferred discovery."""
    toolset = (
        ToolSet.builder()
        .add(example_tool)
        .with_id("diagnostics")
        .with_instructions("Use diagnostics for ambiguous cases.")
        .deferred()
        .build()
    )

    assert [tool.resolved_name() for tool in toolset.tools] == ["example_tool"]
    assert toolset.id == "diagnostics"
    assert toolset.instructions == "Use diagnostics for ambiguous cases."
    assert toolset.defer_loading is True


def test_deferred_extensions_require_stable_ids() -> None:
    """Reject deferred behavior that cannot be resumed by stable identifier."""
    with pytest.raises(ValueError, match="Deferred toolsets require"):
        ToolSet(defer_loading=True)

    with pytest.raises(ValueError, match="Deferred capabilities require"):
        AICapability(defer_loading=True)


def test_skill_loads_agent_skills_markdown_and_attached_tools(
    tmp_path: Path,
) -> None:
    """Load a conforming SKILL.md directory with optional metadata."""
    skill_directory = tmp_path / "closed-failure-review"
    skill_directory.mkdir()
    (skill_directory / "SKILL.md").write_text(
        """---
name: closed-failure-review
description: Use when distinguishing a closed failure from a shutdown.
license: Proprietary
compatibility: Requires temperature history.
metadata:
  owner: reliability
  version: "1"
allowed-tools: compare_shutdown render_chart
---
Compare sensor onset lag, descent slopes, resting temperature, and recovery.
"""
    )

    skill = AISkill.from_path(skill_directory, tools=[example_tool])

    assert skill.name == "closed-failure-review"
    assert skill.id == "closed-failure-review"
    assert skill.defer_loading is True
    assert skill.license == "Proprietary"
    assert skill.compatibility == "Requires temperature history."
    assert skill.metadata == {"owner": "reliability", "version": "1"}
    assert skill.allowed_tools == ("compare_shutdown", "render_chart")
    assert [tool.resolved_name() for tool in skill.tools] == ["example_tool"]
    assert "Compare sensor onset lag" in skill.instructions


def test_skill_loader_discovers_child_skills_in_name_order(tmp_path: Path) -> None:
    """Load a deterministic catalog without scanning unrelated root Markdown."""
    for name in ("zeta-review", "alpha-review"):
        directory = tmp_path / name
        directory.mkdir()
        (directory / "SKILL.md").write_text(
            f"""---
name: {name}
description: Use for {name} cases.
---
Follow the {name} runbook.
"""
        )

    assert [skill.name for skill in load_skills(tmp_path)] == [
        "alpha-review",
        "zeta-review",
    ]


@pytest.mark.parametrize(
    ("directory_name", "skill_name", "expected_message"),
    [
        ("wrong-directory", "valid-name", "must match parent directory"),
        ("Bad_Name", "Bad_Name", "Skill name must be"),
    ],
)
def test_skill_loader_rejects_invalid_agent_skill_names(
    tmp_path: Path,
    directory_name: str,
    skill_name: str,
    expected_message: str,
) -> None:
    """Enforce Agent Skills naming and directory invariants."""
    directory = tmp_path / directory_name
    directory.mkdir()
    (directory / "SKILL.md").write_text(
        f"""---
name: {skill_name}
description: Use for validation tests.
---
Follow the instructions.
"""
    )

    with pytest.raises(ValueError, match=expected_message):
        AISkill.from_path(directory)


def test_capability_and_skill_ids_must_be_unique() -> None:
    """Prevent ambiguous deferred capability catalogs."""
    capability = AICapability(id="diagnostics")
    skill = AISkill(
        name="diagnostics",
        description="Use for diagnostic cases.",
        instructions="Follow the diagnostic runbook.",
    )

    with pytest.raises(ValueError, match="Duplicate capability id: diagnostics"):
        normalize_capabilities([capability], [skill])


class CapabilityOnlyAgent(
    AIAgentMixin[ProcessDataObject, ExampleOutput],
    BaseProcessor[ProcessDataObject],
):
    """Agent that deliberately defines capabilities without standalone tools."""

    output_schema = ExampleOutput

    def _build_system_prompt(self, data_object: ProcessDataObject) -> str:
        """Return stable agent instructions."""
        _ = data_object
        return "Return a value."

    def _build_user_message(self, data_object: ProcessDataObject) -> UserMessage:
        """Return a simple user request."""
        _ = data_object
        return UserMessage().add_text("Return 42.")

    def _build_capabilities(
        self, data_object: ProcessDataObject
    ) -> list[AICapability]:
        """Return one eager capability with a tool."""
        _ = data_object
        return [
            AICapability(
                id="answering",
                instructions="Use the answer tool when needed.",
                tools=[ai_tool(name="answer")(example_tool)],
            )
        ]


class CapturingBackend:
    """Capture the normalized request emitted by an agent mixin."""

    request: AgentRequest[ExampleOutput] | None = None

    def run_agent(
        self,
        request: AgentRequest[ExampleOutput],
        *,
        deps: object | None = None,
    ) -> AgentResult[ExampleOutput]:
        """Store the request and return a deterministic result."""
        _ = deps
        self.request = request
        return AgentResult(output=ExampleOutput(value=42), usage=AIUsage())


def test_capability_only_agent_propagates_extensions_without_build_tools() -> None:
    """Allow processors to rely entirely on capabilities instead of flat tools."""
    backend = CapturingBackend()
    agent = CapabilityOnlyAgent(AIProcessorConfig(model="azure:gpt-5-mini"))
    agent._backend_cache = backend

    agent.process(ProcessDataObject())

    assert backend.request is not None
    assert backend.request.tools == []
    assert [capability.id for capability in backend.request.capabilities] == [
        "answering"
    ]
