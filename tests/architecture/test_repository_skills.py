"""Generated-project-safe contracts for preserved repository skills."""

from __future__ import annotations

import json
from pathlib import Path
import re

import yaml

from workbench.agent_versions.resolver import (
    default_policy_path,
    load_agent_version_policy,
)

ROOT = Path(__file__).resolve().parents[2]
SKILLS = ROOT / ".agents" / "skills"
ROUTING_CASES = ROOT / "tests" / "skill_routing_cases.yaml"
REUSABLE_CHANGE_SKILLS = (
    "agent-improvement-campaign",
    "agent-eval-builder",
    "ai-processor-builder",
    "benchmark-pipeline-port",
    "create-use-case-project",
    "eval-lifecycle",
    "external-runtime-setup",
    "pipeline-builder",
    "port-eval-explorer-use-case",
    "project-guide",
    "publish-retained-eval",
)


def _skill_names() -> set[str]:
    return {path.parent.name for path in SKILLS.glob("*/SKILL.md")}


def _routing_cases() -> list[dict[str, object]]:
    payload = yaml.safe_load(ROUTING_CASES.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    cases = payload["cases"]
    assert isinstance(cases, list)
    return cases


def test_all_repository_skills_stay_under_root_skills_directory() -> None:
    skill_files = tuple(ROOT.glob("**/SKILL.md"))
    repository_skill_files = tuple(
        path
        for path in skill_files
        if ".venv" not in path.parts and "node_modules" not in path.parts
    )

    assert repository_skill_files
    assert all(path.is_relative_to(SKILLS) for path in repository_skill_files)


def test_repository_skill_bodies_stay_concise() -> None:
    skill_files = sorted(SKILLS.glob("*/SKILL.md"))
    line_counts = {
        path.parent.name: len(path.read_text(encoding="utf-8").splitlines())
        for path in skill_files
    }

    assert sum(line_counts.values()) <= 1_400
    assert all(lines <= 190 for lines in line_counts.values()), line_counts


def test_skill_packages_use_only_direct_supported_resources() -> None:
    markdown_link = re.compile(r"\[[^\]]+\]\(([^)#]+\.md)\)")

    for skill in sorted(path for path in SKILLS.iterdir() if path.is_dir()):
        body = (skill / "SKILL.md").read_text(encoding="utf-8")
        for target in markdown_link.findall(body):
            assert (skill / target).resolve().is_file(), (skill.name, target)

        for path in skill.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(skill)
            assert (
                relative == Path("SKILL.md")
                or relative == Path("agents/openai.yaml")
                or (
                    len(relative.parts) == 2
                    and relative.parts[0] == "references"
                    and path.suffix == ".md"
                )
            ), relative

        for reference in (skill / "references").glob("*.md"):
            content = reference.read_text(encoding="utf-8")
            assert not markdown_link.search(content), reference


def test_root_agents_owns_shared_repository_policy() -> None:
    guidance = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    manifest = json.loads((ROOT / "workbench.template.json").read_text())
    ownership = {item["path"]: item["owner"] for item in manifest["ownership"]}

    assert ownership["AGENTS.md"] == "root_infrastructure"
    for required in (
        "Use `workbench.template.json` as the authoritative ownership",
        "Before changing a reusable library or reusable Workbench path",
        "Proceed when the request clearly requires a change",
        "ask\nonce before expanding scope",
        "Use `uv run` for Python commands",
        "verification-matrix.md",
        "quick_validate.py",
        "tests/architecture/test_repository_skills.py",
    ):
        assert required in guidance

    duplicated_policy = "If the request explicitly authorizes the named reusable scope"
    for name in REUSABLE_CHANGE_SKILLS:
        content = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
        assert duplicated_policy not in content, name


def test_skill_descriptions_are_compact_and_disambiguated() -> None:
    descriptions = {}
    for path in sorted(SKILLS.glob("*/SKILL.md")):
        frontmatter = yaml.safe_load(
            path.read_text(encoding="utf-8").split("---", 2)[1]
        )
        descriptions[path.parent.name] = frontmatter["description"]

    assert all(len(description) <= 280 for description in descriptions.values())
    # Keep the router prompt bounded while allowing the dedicated campaign
    # route to describe how it differs from one eval and one candidate.
    assert sum(map(len, descriptions.values())) <= 3_400
    ai_description = descriptions["ai-processor-builder"]
    assert "`mi.ai` runtime" in ai_description
    assert "not Codex `.agents/skills` authoring" in ai_description


def test_all_skill_references_resolve_and_router_covers_every_skill() -> None:
    skill_names = _skill_names()
    reference_pattern = re.compile(r"\$([a-z][a-z0-9-]+)")
    referenced = set()
    for path in sorted(SKILLS.glob("*/SKILL.md")):
        referenced.update(reference_pattern.findall(path.read_text(encoding="utf-8")))

    assert referenced <= skill_names

    guide = (SKILLS / "project-guide" / "SKILL.md").read_text(encoding="utf-8")
    router = guide.split("## Route To Specialized Skills", 1)[1].split(
        "## Improve An Agent Variant", 1
    )[0]
    routed = re.findall(r"\|\s*[^|]+\|\s*`\$([a-z][a-z0-9-]+)`\s*\|", router)
    assert len(routed) == len(set(routed))
    assert set(routed) == skill_names


def test_routing_case_corpus_covers_portfolio_behavior() -> None:
    skill_names = _skill_names()
    cases = _routing_cases()
    allowed_tags = {"positive", "neighbor", "composite", "high_risk", "common_language"}
    allowed_confirmations = {
        "none",
        "authorized_by_prompt",
        "concrete_paid_run",
        "exact_eval_id",
        "exact_retained_eval",
    }

    ids = [case["id"] for case in cases]
    assert len(ids) == len(set(ids))
    for case in cases:
        assert isinstance(case["prompt"], str) and case["prompt"].strip()
        tags = set(case["tags"])
        sequence = case["expected_sequence"]
        excluded = set(case["excluded"])
        assert tags and tags <= allowed_tags
        assert isinstance(sequence, list) and sequence
        assert set(sequence) <= skill_names
        assert excluded <= skill_names
        assert not excluded.intersection(sequence)
        assert case["confirmation"] in allowed_confirmations

    positive_primary = {
        case["expected_sequence"][0] for case in cases if "positive" in case["tags"]
    }
    assert positive_primary == skill_names

    neighbor_cases = [case for case in cases if "neighbor" in case["tags"]]
    assert len(neighbor_cases) >= len(skill_names)
    assert all(case["excluded"] for case in neighbor_cases)

    composite_cases = [case for case in cases if "composite" in case["tags"]]
    assert len(composite_cases) >= 4
    assert all(len(case["expected_sequence"]) >= 2 for case in composite_cases)

    high_risk_cases = [case for case in cases if "high_risk" in case["tags"]]
    assert high_risk_cases
    assert all(case["confirmation"] != "none" for case in high_risk_cases)
    assert {
        "concrete_paid_run",
        "exact_eval_id",
        "exact_retained_eval",
    } <= {case["confirmation"] for case in high_risk_cases}

    common_prompts = " ".join(
        case["prompt"].lower() for case in cases if "common_language" in case["tags"]
    )
    for phrase in (
        "improve the agent",
        "compare these runs",
        "make a new variant",
        "share these results",
    ):
        assert phrase in common_prompts


def test_change_skills_route_to_complete_repository_verification() -> None:
    matrix_path = SKILLS / "project-guide" / "references" / "verification-matrix.md"
    matrix = matrix_path.read_text(encoding="utf-8")

    for required in (
        "uv run pytest <nearest-test-paths> -q",
        "uv run ruff check <changed-python-paths>",
        "uv run basedpyright",
        "explicitly versioned published example",
        "uv run pytest packages/mi-core/tests/<area> -q",
        "pnpm test",
        "pnpm build",
        "quick_validate.py",
        "tests/architecture/test_repository_skills.py",
        "git diff --check",
    ):
        assert required in matrix

    for name in REUSABLE_CHANGE_SKILLS:
        content = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
        assert "verification-matrix.md" in content, name


def test_create_project_skill_has_valid_discovery_metadata() -> None:
    skill = SKILLS / "create-use-case-project"
    content = (skill / "SKILL.md").read_text(encoding="utf-8")
    frontmatter = yaml.safe_load(content.split("---", 2)[1])
    interface = yaml.safe_load(
        (skill / "agents/openai.yaml").read_text(encoding="utf-8")
    )["interface"]

    assert frontmatter["name"] == "create-use-case-project"
    assert "separate Agent Workbench" in frontmatter["description"]
    assert interface["display_name"] == "Create Use Case Project"
    assert "$create-use-case-project" in interface["default_prompt"]
    assert "reusable `model-pricing.yaml` remains valid" in content
    assert "`model-pricing.yaml` contain the new project identity" not in content


def test_project_configured_skills_do_not_hard_code_reference_identity() -> None:
    manifest = json.loads((ROOT / "workbench.template.json").read_text())
    forbidden = tuple(manifest["reference_reset"]["forbidden_terms"])
    for name in ("run-use-case-evals", "external-runtime-setup"):
        content = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8").lower()
        assert not any(term in content for term in forbidden), name


def test_retained_eval_publication_skill_matches_product_and_code() -> None:
    publication = (SKILLS / "publish-retained-eval" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    lifecycle = (SKILLS / "eval-lifecycle" / "SKILL.md").read_text(encoding="utf-8")
    builder = (SKILLS / "agent-eval-builder" / "SKILL.md").read_text(encoding="utf-8")
    guide = (SKILLS / "project-guide" / "SKILL.md").read_text(encoding="utf-8")
    contracts = (
        SKILLS / "agent-eval-builder" / "references" / "current-evaluation-contracts.md"
    ).read_text(encoding="utf-8")
    strategy_path = ROOT / "docs/product-strategy/mvp-scope.md"

    assert (ROOT / "workbench/eval_publication/cli.py").is_file()
    if strategy_path.is_file():
        strategy = strategy_path.read_text(encoding="utf-8")
        assert "explicitly publish selected complete retained eval results" in strategy
    assert "workbench.eval_publication.cli" in publication
    assert "--dry-run" in publication
    assert "--yes" in publication
    assert "publication-manifest.json" in publication
    assert "$publish-retained-eval" in lifecycle
    assert "$publish-retained-eval" in builder
    assert "$publish-retained-eval" in guide
    assert "workbench/eval_publication/" in contracts
    for content in (lifecycle, builder):
        assert "cloud publication is post-mvp" not in content.lower()


def test_ai_processor_skill_uses_registry_discoverable_typed_config() -> None:
    content = (SKILLS / "ai-processor-builder" / "SKILL.md").read_text(encoding="utf-8")

    for required in (
        "config: ClassificationProcessorConfig",
        "config: ClassificationProcessorConfig | None = None",
        "resolved_config = config or ClassificationProcessorConfig()",
        "super().__init__(resolved_config)",
        "self.config = resolved_config",
    ):
        assert required in content


def test_ai_processor_skill_does_not_require_static_f_strings() -> None:
    content = (SKILLS / "ai-processor-builder" / "SKILL.md").read_text(encoding="utf-8")

    assert "Use plain strings for static prompts" in content
    assert "explicit f-strings" not in content
    assert 'return f"You classify' not in content


def test_every_evaluable_pipeline_has_a_valid_matching_agent_policy() -> None:
    pipelines = sorted((ROOT / "use_case/pipeline_configs").glob("*.ppln"))
    for pipeline in pipelines:
        policy_path = default_policy_path(pipeline, root=ROOT)
        assert policy_path.is_file(), pipeline.name
        policy = load_agent_version_policy(policy_path)
        assert (policy_path.parent / policy.source_pipeline).resolve() == (
            pipeline.resolve()
        )
        structured_input = policy.contracts.get("structured_input")
        structured_output = policy.contracts.get("structured_output")
        action_policy = policy.contracts.get("action_policy")
        evidence_recipe = policy.contracts.get("evidence_recipe")
        assert isinstance(structured_input, dict) and structured_input
        assert isinstance(structured_output, dict) and structured_output
        assert isinstance(action_policy, dict) and action_policy
        assert isinstance(evidence_recipe, dict) and evidence_recipe
        assert policy.model_policy.permitted_overrides.models
        assert policy.model_policy.permitted_overrides.reasoning_efforts


def test_pipeline_skill_requires_explicit_version_for_recorded_validation() -> None:
    content = (SKILLS / "pipeline-builder" / "SKILL.md").read_text(encoding="utf-8")

    assert "Require explicit benchmark version and example identity" in content
    assert "latest-version resolution only for interactive discovery" in content
    assert "benchmark version may resolve to the latest" not in content


def test_pipeline_skill_matches_candidate_asset_ownership() -> None:
    content = (SKILLS / "pipeline-builder" / "SKILL.md").read_text(encoding="utf-8")

    assert "`version_assets()` and\n`version_contracts()`" in content
    assert "`additional_assets` only for behavior-bearing files" in content
    assert "prove the complete graph was captured" in content


def test_lifecycle_skill_defines_complete_selected_occurrence() -> None:
    lifecycle = (SKILLS / "eval-lifecycle" / "SKILL.md").read_text(encoding="utf-8")
    contracts = (
        SKILLS / "agent-eval-builder" / "references/current-evaluation-contracts.md"
    ).read_text(encoding="utf-8")

    for content in (lifecycle, contracts):
        assert "complete selected occurrence" in content
        assert "complete full run" not in content.lower()
        assert "full-run elevation" not in content.lower()
    assert "every planned work item" in lifecycle
    assert "zero planned work items are missing" in " ".join(contracts.split())


def test_explorer_port_skill_supports_working_and_retained_evidence() -> None:
    content = (SKILLS / "port-eval-explorer-use-case" / "SKILL.md").read_text(
        encoding="utf-8"
    )

    assert "working occurrence:" in content
    assert "retained occurrence:" in content
    assert "lifecycle-verified bundle" in content
    assert "equivalent working and retained inputs" in content


def test_eval_analysis_distinguishes_working_and_retained_handoffs() -> None:
    content = (SKILLS / "eval-results-analysis" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    frontmatter = yaml.safe_load(content.split("---", 2)[1])

    for change_type in ("model", "tool", "grader", "configuration", "evidence"):
        assert change_type in frontmatter["description"]
    assert "That command resolves\n   working evals only." in content
    assert "keep its bundle immutable" in content
    assert "outside the retained bundle" in content
    assert "evidence-grounded explanations" in content
    assert "chart-grounded explanations" not in content
    assert "only when the selected use-case adapter supplies charts" in content
    assert "workbench.eval_lifecycle.cli verify <retained-id> --json" in content
    assert content.index("verify <retained-id>") < content.index("units.json")


def test_eval_runner_skill_documents_occurrence_and_dry_run_contracts() -> None:
    content = (SKILLS / "run-use-case-evals" / "SKILL.md").read_text(encoding="utf-8")

    assert "one new occurrence of the requested scope" in content
    assert "Eval `--dry-run` is stateful" in content
    assert "emitted `--run-id` command" in content
    assert "selected examples\n   × repetitions" in content
    assert "available frozen\n   pricing basis" in content


def test_skills_assign_generated_eval_runbook_ownership() -> None:
    create = (SKILLS / "create-use-case-project" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    port = (SKILLS / "benchmark-pipeline-port" / "SKILL.md").read_text(encoding="utf-8")
    builder = (SKILLS / "agent-eval-builder" / "SKILL.md").read_text(encoding="utf-8")
    runner = (SKILLS / "run-use-case-evals" / "SKILL.md").read_text(encoding="utf-8")
    marker = "agent-workbench-eval-runbook-status: bootstrap-placeholder"

    assert "marked bootstrap placeholder" in create
    assert marker in port
    assert marker in builder
    assert marker in runner
    assert "do not infer or" in runner.lower()


def test_preserved_skills_treat_removed_product_strategy_as_optional() -> None:
    manifest = json.loads((ROOT / "workbench.template.json").read_text())
    removed = manifest["reference_reset"]["remove_directories"]
    assert "docs/product-strategy" in removed

    for name in ("project-guide", "agent-eval-builder"):
        content = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
        normalized = " ".join(content.split())
        assert "docs/product-strategy/" in content
        assert (
            "when that template-repository directory exists" in normalized
            or "when it exists" in normalized
        )
        assert "workbench.project.json" in content
        assert "use_case/docs/" in content


def test_project_guide_uses_manifest_paths_and_unique_routes() -> None:
    content = (SKILLS / "project-guide" / "SKILL.md").read_text(encoding="utf-8")
    layout = content.split("## Repository Layout", 1)[1].split("## Gate New Work", 1)[0]
    routes = content.split("## Route To Specialized Skills", 1)[1].split(
        "## Guide Template Customization", 1
    )[0]

    assert "`workbench.template.json` as the authoritative path inventory" in layout
    assert "`data/`" not in layout
    assert "workbench/experimental_core" not in content
    assert "| Task | Skill |" in routes
    assert "Follow root `AGENTS.md`" in content
    assert "Use `uv run` for Python commands" not in content
    assert "Run commands with `uv run`" not in content


def test_project_guide_defines_measured_agent_improvement_loop() -> None:
    content = (SKILLS / "project-guide" / "SKILL.md").read_text(encoding="utf-8")
    loop = content.split("## Improve An Agent Variant", 1)[1].split(
        "## Guide Template Customization", 1
    )[0]
    improvement_case = next(
        case for case in _routing_cases() if case["id"] == "improve_agent"
    )
    routed_sequence = improvement_case["expected_sequence"][1:]
    cursor = 0
    for skill in routed_sequence:
        cursor = loop.index(f"${skill}", cursor) + len(skill) + 1

    loop_references = set(re.findall(r"\$([a-z][a-z0-9-]+)", loop))
    assert {
        "agent-eval-builder",
        "ai-processor-builder",
        "eval-lifecycle",
        "publish-retained-eval",
    } <= loop_references


def test_single_eval_and_campaign_routes_cannot_substitute_for_each_other() -> None:
    guide = (SKILLS / "project-guide" / "SKILL.md").read_text(encoding="utf-8")
    campaign = (
        SKILLS / "agent-improvement-campaign" / "SKILL.md"
    ).read_text(encoding="utf-8")
    cases = {case["id"]: case for case in _routing_cases()}

    assert cases["broad_paid_eval"]["expected_sequence"] == ["run-use-case-evals"]
    assert "agent-improvement-campaign" in cases["broad_paid_eval"]["excluded"]
    assert cases["run_improvement_campaign"]["expected_sequence"] == [
        "agent-improvement-campaign"
    ]
    assert "run-use-case-evals" in cases["run_improvement_campaign"]["excluded"]
    assert "Never turn a single-eval request" in guide
    assert "Never reduce\nan authorized campaign to one ordinary eval" in guide
    assert "Use this skill only for an explicit multi-attempt campaign" in campaign
    assert "Do not use for one eval" in campaign


def test_campaign_requires_post_research_qualification_confirmation() -> None:
    campaign = (
        SKILLS / "agent-improvement-campaign" / "SKILL.md"
    ).read_text(encoding="utf-8")
    ledger = (
        SKILLS
        / "agent-improvement-campaign"
        / "references"
        / "campaign-ledger.md"
    ).read_text(encoding="utf-8")

    assert "Qualification reserve is planning capacity, not authorization" in campaign
    assert "Do not allocate or run qualification until the user explicitly confirms" in (
        campaign
    )
    assert "stop with the research winner and skip qualification" in campaign
    assert "qualification_skipped" in campaign
    assert "`qualification_decision`" in ledger
    assert "`pending`,\n  `authorized`, or `declined`" in ledger


def test_campaign_and_analysis_require_use_case_evidence_review() -> None:
    campaign = (
        SKILLS / "agent-improvement-campaign" / "SKILL.md"
    ).read_text(encoding="utf-8")
    analysis = (
        SKILLS / "eval-results-analysis" / "SKILL.md"
    ).read_text(encoding="utf-8")

    assert "inspect the exact\n   captured artifacts" in campaign
    assert "Quantify reviewer-note and verification coverage" in campaign
    assert "publication boundary" in campaign
    assert "Directly\n   inspect the exact captured rich artifacts" in analysis
    assert "Quantify populated versus missing context" in analysis
    assert "publication\n   evidence-integrity mismatch" in analysis


def test_current_evaluation_contracts_state_schema_boundaries() -> None:
    contracts = (
        SKILLS / "agent-eval-builder" / "references" / "current-evaluation-contracts.md"
    ).read_text(encoding="utf-8")

    assert "selected immutable attempt-generation files" in contracts
    assert "Legacy schema-v1 working bundles are rejected" in contracts
    assert "Elevation always creates a schema-v2 retained eval" in contracts
    assert "Publication accepts schema-v2 retained evals only" in contracts
    assert "retained attempt generations" not in contracts


def test_skill_ui_metadata_uses_one_human_facing_convention() -> None:
    display_names = []
    for name in sorted(_skill_names()):
        metadata = yaml.safe_load(
            (SKILLS / name / "agents/openai.yaml").read_text(encoding="utf-8")
        )
        interface = metadata["interface"]
        display_name = interface["display_name"]
        display_names.append(display_name)

        assert "-" not in display_name
        assert all(
            token == "mi.ai" or token[0].isupper() for token in display_name.split()
        )
        assert 25 <= len(interface["short_description"]) <= 64
        assert f"${name}" in interface["default_prompt"]

    assert len(display_names) == len(set(display_names))
