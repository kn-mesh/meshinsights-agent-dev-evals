"""Backend-neutral capabilities and Agent Skills support for mi.ai agents."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Any, Sequence

import yaml

from mi.ai.tools import Tool, ToolCollectionLike, ToolSet, normalize_tools

_SKILL_NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass(slots=True)
class AICapability:
    """Bundle related instructions, tools, and toolsets for an agent."""

    instructions: str | None = None
    tools: list[Tool] = field(default_factory=list)
    toolsets: list[ToolSet] = field(default_factory=list)
    id: str | None = None
    description: str | None = None
    defer_loading: bool = False

    def __post_init__(self) -> None:
        if self.defer_loading and not self.id:
            raise ValueError("Deferred capabilities require a stable id")


@dataclass(slots=True)
class AISkill:
    """Agent Skills-compatible instructions loaded as an AI capability."""

    name: str
    description: str
    instructions: str
    tools: list[Tool] = field(default_factory=list)
    toolsets: list[ToolSet] = field(default_factory=list)
    defer_loading: bool = True
    license: str | None = None
    compatibility: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)
    allowed_tools: tuple[str, ...] = ()
    source_path: Path | None = None

    def __post_init__(self) -> None:
        _validate_skill_name(self.name)
        _validate_skill_description(self.description)
        if not self.instructions.strip():
            raise ValueError("Skill instructions must not be empty")

    @property
    def id(self) -> str:
        """Return the capability identifier used for skill discovery."""
        return self.name

    def as_capability(self) -> AICapability:
        """Convert this skill into the shared capability contract."""
        return AICapability(
            id=self.name,
            description=self.description,
            instructions=self.instructions,
            tools=list(self.tools),
            toolsets=list(self.toolsets),
            defer_loading=self.defer_loading,
        )

    @classmethod
    def from_path(
        cls,
        path: str | Path,
        *,
        tools: ToolCollectionLike = (),
        toolsets: Sequence[ToolSet] = (),
        defer_loading: bool = True,
    ) -> "AISkill":
        """Load and validate an Agent Skills directory or Markdown file."""
        requested_path = Path(path)
        skill_path = (
            requested_path / "SKILL.md" if requested_path.is_dir() else requested_path
        )
        if not skill_path.is_file():
            raise ValueError(f"Skill file does not exist: {skill_path}")

        metadata, instructions = _parse_skill_markdown(skill_path.read_text())
        name = _required_string(metadata, "name")
        description = _required_string(metadata, "description")
        if skill_path.name == "SKILL.md" and skill_path.parent.name != name:
            raise ValueError(
                f"Skill name {name!r} must match parent directory "
                f"{skill_path.parent.name!r}"
            )

        raw_metadata = metadata.get("metadata", {})
        if raw_metadata is None:
            raw_metadata = {}
        if not isinstance(raw_metadata, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in raw_metadata.items()
        ):
            raise ValueError("Skill metadata must map strings to strings")

        license_value = _optional_string(metadata, "license")
        compatibility = _optional_string(metadata, "compatibility")
        if compatibility is not None and len(compatibility) > 500:
            raise ValueError("Skill compatibility must be at most 500 characters")

        allowed_tools_value = metadata.get("allowed-tools")
        if allowed_tools_value is None:
            allowed_tools: tuple[str, ...] = ()
        elif isinstance(allowed_tools_value, str):
            allowed_tools = tuple(allowed_tools_value.split())
        else:
            raise ValueError("Skill allowed-tools must be a space-separated string")

        return cls(
            name=name,
            description=description,
            instructions=instructions,
            tools=normalize_tools(tools),
            toolsets=list(toolsets),
            defer_loading=defer_loading,
            license=license_value,
            compatibility=compatibility,
            metadata=dict(raw_metadata),
            allowed_tools=allowed_tools,
            source_path=skill_path.resolve(),
        )


def load_skills(
    directory: str | Path,
    *,
    recursive: bool = False,
) -> list[AISkill]:
    """Load Agent Skills from child directories in deterministic name order."""
    root = Path(directory)
    if not root.is_dir():
        raise ValueError(f"Skills directory does not exist: {root}")
    pattern = "**/SKILL.md" if recursive else "*/SKILL.md"
    return [AISkill.from_path(path) for path in sorted(root.glob(pattern))]


def normalize_capabilities(
    capabilities: Sequence[AICapability],
    skills: Sequence[AISkill],
) -> list[AICapability]:
    """Combine capabilities and skills while rejecting duplicate identifiers."""
    normalized = [*capabilities, *(skill.as_capability() for skill in skills)]
    seen_ids: set[str] = set()
    for capability in normalized:
        if capability.id is None:
            continue
        if capability.id in seen_ids:
            raise ValueError(f"Duplicate capability id: {capability.id}")
        seen_ids.add(capability.id)
    return normalized


def _parse_skill_markdown(source: str) -> tuple[dict[str, Any], str]:
    """Split one SKILL.md document into validated frontmatter and instructions."""
    lines = source.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("Skill Markdown must start with YAML frontmatter")
    try:
        closing_index = next(
            index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---"
        )
    except StopIteration as exc:
        raise ValueError("Skill Markdown frontmatter is missing its closing delimiter") from exc

    raw_frontmatter = "\n".join(lines[1:closing_index])
    loaded = yaml.safe_load(raw_frontmatter)
    if not isinstance(loaded, dict):
        raise ValueError("Skill Markdown frontmatter must be a YAML mapping")
    instructions = "\n".join(lines[closing_index + 1 :]).strip()
    return loaded, instructions


def _required_string(metadata: dict[str, Any], field_name: str) -> str:
    value = metadata.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Skill {field_name} must be a non-empty string")
    return value.strip()


def _optional_string(metadata: dict[str, Any], field_name: str) -> str | None:
    value = metadata.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Skill {field_name} must be a non-empty string")
    return value.strip()


def _validate_skill_name(name: str) -> None:
    if len(name) > 64 or not _SKILL_NAME_PATTERN.fullmatch(name):
        raise ValueError(
            "Skill name must be at most 64 characters and contain only lowercase "
            "letters, numbers, and single hyphens"
        )


def _validate_skill_description(description: str) -> None:
    if not description.strip() or len(description) > 1024:
        raise ValueError("Skill description must contain 1 to 1024 characters")
