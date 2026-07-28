from __future__ import annotations

import json
from pathlib import Path

import pytest

from workbench.apps.improvement_campaigns import ImprovementCampaignReader


def _write_campaign(root: Path, campaign_id: str = "imp_test") -> Path:
    campaign_dir = root / ".workbench/improvements" / campaign_id
    campaign_dir.mkdir(parents=True)
    campaign = {
        "schema_version": 1,
        "campaign_id": campaign_id,
        "created_at_utc": "2026-07-28T12:00:00Z",
        "starting_agent": {
            "git_commit": "abc123",
            "agent_version_id": "av_start",
            "selection_summary": "User selected an alternate lineage.",
        },
        "source": {},
        "world": {
            "benchmark_key": "benchmark",
            "benchmark_version": 7,
            "research_scope": {"section": "development"},
            "qualification_scope": {"all_examples": True},
            "runtime_configurations": [
                {
                    "id": "primary",
                    "role": "selection",
                    "model": "provider:primary",
                    "reasoning_effort": "medium",
                },
                {
                    "id": "comparison",
                    "role": "comparison",
                    "model": "provider:comparison",
                    "reasoning_effort": "low",
                },
            ],
            "selection_configuration_id": "primary",
        },
        "acceptance": {
            "primary_metric": "complete_evaluation_accuracy",
            "direction": "maximize",
        },
        "limits": {"max_attempts": 4},
    }
    state = {
        "schema_version": 1,
        "status": "complete",
        "termination_reason": "max_attempts",
        "baseline_evaluations": [
            {
                "configuration_id": "primary",
                "eval_id": "eval_base_primary",
                "primary_metric": 0.7,
                "cost": 1.0,
            },
            {
                "configuration_id": "comparison",
                "eval_id": "eval_base_comparison",
                "primary_metric": 0.68,
                "cost": 0.5,
            },
        ],
        "incumbent_agent_version_id": "av_winner",
        "attempts_finished": 2,
        "stored_total_cost": 4.5,
        "qualification_evaluations": [
            {
                "configuration_id": "primary",
                "eval_id": "eval_qualification",
                "primary_metric": 0.82,
                "cost": 1.2,
            }
        ],
    }
    trials = [
        {
            "trial": 1,
            "candidate_commit": "def456",
            "agent_version_id": "av_one",
            "hypothesis": "Clarify one rule.",
            "change_summary": "Added one focused rule.",
            "changed_paths": ["use_case/prompt.py"],
            "evaluations": [
                {
                    "configuration_id": "primary",
                    "eval_id": "eval_one",
                    "primary_metric": 0.75,
                    "cost": 1.0,
                },
                {
                    "configuration_id": "comparison",
                    "eval_id": "eval_one_comparison",
                    "primary_metric": 0.7,
                    "cost": 0.5,
                },
            ],
            "decision": "keep",
            "decision_summary": "Improved without regression.",
        },
        {
            "trial": 2,
            "candidate_commit": "ghi789",
            "agent_version_id": "av_two",
            "hypothesis": "Try a longer prompt.",
            "change_summary": "Expanded prompt context.",
            "changed_paths": ["use_case/prompt.py"],
            "evaluations": [
                {
                    "configuration_id": "primary",
                    "eval_id": "eval_two",
                    "primary_metric": 0.72,
                    "cost": 0.8,
                }
            ],
            "decision": "discard",
            "decision_summary": "Regressed on the selection configuration.",
        },
    ]
    (campaign_dir / "campaign.json").write_text(
        json.dumps(campaign), encoding="utf-8"
    )
    (campaign_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")
    (campaign_dir / "trials.jsonl").write_text(
        "\n".join(json.dumps(item) for item in trials) + "\n", encoding="utf-8"
    )
    return campaign_dir


def test_campaign_reader_projects_summary_points_and_change_history(
    tmp_path: Path,
) -> None:
    _write_campaign(tmp_path)
    reader = ImprovementCampaignReader(tmp_path)

    listed = reader.list_campaigns()
    detail = reader.get_campaign("imp_test")

    assert listed["findings"] == []
    assert listed["campaigns"][0]["starting_agent"]["agent_version_id"] == "av_start"
    assert listed["campaigns"][0]["baseline_metric"] == 0.7
    assert listed["campaigns"][0]["best_metric"] == 0.75
    assert listed["campaigns"][0]["outcomes"] == {
        "keep": 1,
        "discard": 1,
        "inconclusive": 0,
        "crash": 0,
    }
    assert {point["configuration_id"] for point in detail["points"]} == {
        "primary",
        "comparison",
    }
    assert any(point["stage"] == "qualification" for point in detail["points"])
    assert detail["trials"][0]["change_summary"] == "Added one focused rule."


def test_campaign_list_isolates_malformed_ledgers(tmp_path: Path) -> None:
    _write_campaign(tmp_path)
    broken = tmp_path / ".workbench/improvements/imp_broken"
    broken.mkdir(parents=True)
    (broken / "campaign.json").write_text("{", encoding="utf-8")
    (broken / "state.json").write_text("{}", encoding="utf-8")
    (broken / "trials.jsonl").write_text("", encoding="utf-8")

    payload = ImprovementCampaignReader(tmp_path).list_campaigns()

    assert [item["campaign_id"] for item in payload["campaigns"]] == ["imp_test"]
    assert payload["findings"][0]["campaign_id"] == "imp_broken"
    assert payload["findings"][0]["code"] == "invalid_campaign"


def test_campaign_reader_rejects_invalid_or_escaping_ids(tmp_path: Path) -> None:
    reader = ImprovementCampaignReader(tmp_path)

    with pytest.raises(ValueError, match="Invalid improvement campaign ID"):
        reader.get_campaign("../outside")
