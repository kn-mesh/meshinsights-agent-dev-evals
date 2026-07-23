"""Contract tests for root-level repository skill ownership and approval gates."""

from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / ".agents" / "skills"
REUSABLE_CHANGE_SKILLS = (
    "agent-eval-builder",
    "ai-processor-builder",
    "benchmark-pipeline-port",
    "create-use-case-project",
    "eval-lifecycle",
    "external-runtime-setup",
    "pipeline-builder",
    "port-eval-explorer-use-case",
    "project-guide",
)


def test_all_repository_skills_stay_under_root_skills_directory() -> None:
    skill_files = tuple(ROOT.glob("**/SKILL.md"))
    repository_skill_files = tuple(
        path
        for path in skill_files
        if ".venv" not in path.parts and "node_modules" not in path.parts
    )

    assert repository_skill_files
    assert all(path.is_relative_to(SKILLS) for path in repository_skill_files)


def test_reusable_change_skills_require_explicit_user_approval() -> None:
    for name in REUSABLE_CHANGE_SKILLS:
        content = " ".join(
            (SKILLS / name / "SKILL.md").read_text(encoding="utf-8").lower().split()
        )
        assert "explicit user approval" in content, name


def test_create_project_skill_has_valid_discovery_metadata() -> None:
    skill = SKILLS / "create-use-case-project"
    content = (skill / "SKILL.md").read_text(encoding="utf-8")
    frontmatter = yaml.safe_load(content.split("---", 2)[1])
    interface = yaml.safe_load(
        (skill / "agents/openai.yaml").read_text(encoding="utf-8")
    )["interface"]

    assert frontmatter["name"] == "create-use-case-project"
    assert "separate Git repository" in frontmatter["description"]
    assert interface["display_name"] == "Create Use-Case Project"
    assert "$create-use-case-project" in interface["default_prompt"]


def test_project_configured_skills_do_not_hard_code_reference_identity() -> None:
    forbidden = ("spirax", "steam trap", "steam-trap", "v1_3", "misprx")
    for name in ("run-use-case-evals", "external-runtime-setup"):
        content = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8").lower()
        assert not any(term in content for term in forbidden), name
