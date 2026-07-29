"""Read-only projection of generated-local agent improvement campaigns."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any


_CAMPAIGN_ID = re.compile(r"imp_[A-Za-z0-9][A-Za-z0-9_-]{0,95}")
_DECISIONS = ("keep", "discard", "inconclusive", "crash")


class ImprovementCampaignReader:
    """Load the disposable three-file campaign ledger for human review."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self.root = (self.project_root / ".workbench/improvements").resolve()

    def list_campaigns(self) -> dict[str, Any]:
        campaigns: list[dict[str, Any]] = []
        findings: list[dict[str, str]] = []
        if not self.root.is_dir():
            return {"campaigns": campaigns, "findings": findings}

        for candidate in sorted(self.root.iterdir()):
            if not candidate.is_dir() or not _CAMPAIGN_ID.fullmatch(candidate.name):
                continue
            try:
                detail = self.get_campaign(candidate.name)
            except (OSError, ValueError, json.JSONDecodeError) as error:
                findings.append(
                    {
                        "campaign_id": candidate.name,
                        "code": "invalid_campaign",
                        "message": str(error),
                    }
                )
                continue
            campaigns.append(_summary(detail))

        campaigns.sort(
            key=lambda item: str(item.get("created_at_utc") or ""), reverse=True
        )
        return {"campaigns": campaigns, "findings": findings}

    def eval_campaign_ids(self) -> dict[str, list[str]]:
        """Index exact eval occurrences by the campaigns that recorded them."""
        index: dict[str, set[str]] = {}
        if not self.root.is_dir():
            return {}
        for candidate in sorted(self.root.iterdir()):
            if not candidate.is_dir() or not _CAMPAIGN_ID.fullmatch(candidate.name):
                continue
            try:
                detail = self.get_campaign(candidate.name)
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            for point in detail["points"]:
                eval_id = point.get("eval_id")
                if isinstance(eval_id, str) and eval_id:
                    index.setdefault(eval_id, set()).add(candidate.name)
        return {
            eval_id: sorted(campaign_ids)
            for eval_id, campaign_ids in sorted(index.items())
        }

    def get_campaign(self, campaign_id: str) -> dict[str, Any]:
        campaign_dir = self._campaign_dir(campaign_id)
        if not campaign_dir.is_dir():
            raise FileNotFoundError(f"Unknown improvement campaign: {campaign_id}")

        campaign = _read_object(campaign_dir / "campaign.json")
        state = _read_object(campaign_dir / "state.json")
        trials = _read_json_lines(campaign_dir / "trials.jsonl")
        if campaign.get("schema_version") != 1 or state.get("schema_version") != 1:
            raise ValueError("Campaign and state must use schema_version 1.")
        if campaign.get("campaign_id") != campaign_id:
            raise ValueError("Campaign ID does not match its directory.")

        starting_agent = _object(campaign.get("starting_agent"), "starting_agent")
        source = _object(campaign.get("source"), "source")
        world = _object(campaign.get("world"), "world")
        limits = _object(campaign.get("limits"), "limits")
        acceptance = _object(campaign.get("acceptance"), "acceptance")
        configurations = _runtime_configurations(world)
        selection_id = _string(
            world.get("selection_configuration_id"), "selection_configuration_id"
        )
        if selection_id not in {item["id"] for item in configurations}:
            raise ValueError("Selection configuration is not declared.")

        points = _campaign_points(
            state=state,
            trials=trials,
            selection_id=selection_id,
            starting_agent_id=starting_agent.get("agent_version_id"),
        )
        selection_values = [
            item["primary_metric"]
            for item in points
            if item["configuration_id"] == selection_id
            and item["stage"] in {"baseline", "trial"}
            and isinstance(item["primary_metric"], (int, float))
        ]
        direction = acceptance.get("direction", "maximize")
        best_metric = (
            (min(selection_values) if direction == "minimize" else max(selection_values))
            if selection_values
            else None
        )
        baseline_metric = next(
            (
                item["primary_metric"]
                for item in points
                if item["configuration_id"] == selection_id
                and item["stage"] == "baseline"
            ),
            None,
        )
        outcomes = {decision: 0 for decision in _DECISIONS}
        for trial in trials:
            decision = trial.get("decision")
            if decision in outcomes:
                outcomes[decision] += 1

        return {
            "campaign_id": campaign_id,
            "status": str(state.get("status") or "unknown"),
            "created_at_utc": campaign.get("created_at_utc"),
            "completed_at_utc": (
                state.get("finished_at_utc")
                or state.get("research_completed_at_utc")
            ),
            "termination_reason": state.get("termination_reason"),
            "starting_agent": {
                "git_commit": starting_agent.get("git_commit"),
                "agent_version_id": starting_agent.get("agent_version_id"),
                "selection_summary": starting_agent.get("selection_summary"),
            },
            "base_agent_name": _base_agent_name(source.get("pipeline")),
            "benchmark_key": world.get("benchmark_key"),
            "benchmark_version": world.get("benchmark_version"),
            "research_scope": world.get("research_scope"),
            "qualification_scope": world.get("qualification_scope"),
            "runtime_configurations": configurations,
            "selection_configuration_id": selection_id,
            "primary_metric": acceptance.get("primary_metric"),
            "direction": direction,
            "attempts_finished": _integer(
                state.get("attempts_finished"),
                default=_integer(state.get("finished_attempts"), default=0),
            ),
            "max_attempts": _integer(limits.get("max_attempts"), default=0),
            "stored_total_cost": _number(state.get("stored_total_cost"), default=0.0),
            "baseline_metric": baseline_metric,
            "best_metric": best_metric,
            "outcomes": outcomes,
            "points": points,
            "trials": trials,
        }

    def _campaign_dir(self, campaign_id: str) -> Path:
        if not _CAMPAIGN_ID.fullmatch(campaign_id):
            raise ValueError(f"Invalid improvement campaign ID: {campaign_id}")
        candidate = (self.root / campaign_id).resolve()
        if candidate.parent != self.root:
            raise ValueError("Campaign path escapes the improvements root.")
        return candidate


def _summary(detail: dict[str, Any]) -> dict[str, Any]:
    return {
        key: detail[key]
        for key in (
            "campaign_id",
            "status",
            "created_at_utc",
            "completed_at_utc",
            "termination_reason",
            "starting_agent",
            "base_agent_name",
            "benchmark_key",
            "benchmark_version",
            "research_scope",
            "qualification_scope",
            "runtime_configurations",
            "selection_configuration_id",
            "primary_metric",
            "attempts_finished",
            "max_attempts",
            "stored_total_cost",
            "baseline_metric",
            "best_metric",
            "outcomes",
        )
    }


def _campaign_points(
    *,
    state: dict[str, Any],
    trials: list[dict[str, Any]],
    selection_id: str,
    starting_agent_id: Any,
) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    for evaluation in _evaluation_objects(state.get("baseline_evaluations")):
        points.append(
            _point(
                evaluation,
                stage="baseline",
                trial=0,
                decision="baseline",
                agent_version_id=starting_agent_id,
            )
        )

    last_trial = 0
    for trial in trials:
        trial_number = _integer(trial.get("trial"), default=last_trial + 1)
        last_trial = max(last_trial, trial_number)
        for evaluation in _objects(trial.get("evaluations")):
            points.append(
                _point(
                    evaluation,
                    stage="trial",
                    trial=trial_number,
                    decision=str(trial.get("decision") or "unknown"),
                    agent_version_id=trial.get("agent_version_id"),
                )
            )

    incumbent = state.get("incumbent")
    incumbent_agent_version_id = (
        incumbent.get("agent_version_id")
        if isinstance(incumbent, dict)
        else state.get("incumbent_agent_version_id")
    )
    for evaluation in _evaluation_objects(state.get("qualification_evaluations")):
        points.append(
            _point(
                evaluation,
                stage="qualification",
                trial=last_trial + 1,
                decision="qualification",
                agent_version_id=incumbent_agent_version_id,
            )
        )

    declared = {item["configuration_id"] for item in points}
    if points and selection_id not in declared:
        raise ValueError("Campaign ledger has no selection-configuration evaluations.")
    return points


def _point(
    evaluation: dict[str, Any],
    *,
    stage: str,
    trial: int,
    decision: str,
    agent_version_id: Any,
) -> dict[str, Any]:
    return {
        "stage": stage,
        "trial": trial,
        "configuration_id": evaluation.get("configuration_id"),
        "eval_id": evaluation.get("eval_id"),
        "primary_metric": evaluation.get("primary_metric"),
        "scoring_coverage": evaluation.get("scoring_coverage"),
        "critical_regressions": evaluation.get("critical_regressions"),
        "cost": evaluation.get("cost"),
        "decision": decision,
        "agent_version_id": agent_version_id,
    }


def _runtime_configurations(world: dict[str, Any]) -> list[dict[str, Any]]:
    configurations = []
    for raw in _objects(world.get("runtime_configurations")):
        configurations.append(
            {
                "id": _string(raw.get("id"), "runtime configuration id"),
                "role": raw.get("role"),
                "model": raw.get("model"),
                "reasoning_effort": raw.get("reasoning_effort"),
            }
        )
    if not configurations:
        raise ValueError("Campaign must declare at least one runtime configuration.")
    return configurations


def _read_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return _object(payload, path.name)


def _read_json_lines(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"Missing campaign ledger: {path.name}")
    records = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        payload = json.loads(line)
        records.append(_object(payload, f"{path.name}:{line_number}"))
    return records


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object.")
    return value


def _objects(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError("Campaign evaluation collections must be arrays of objects.")
    return value


def _evaluation_objects(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, list):
        return _objects(value)
    if not isinstance(value, dict):
        raise ValueError(
            "Campaign evaluation collections must be arrays or configuration maps."
        )

    evaluations = []
    for configuration_id, raw in value.items():
        if isinstance(raw, dict):
            evaluation = dict(raw)
            evaluation.setdefault("configuration_id", configuration_id)
        elif isinstance(raw, str) and raw:
            evaluation = {
                "configuration_id": configuration_id,
                "eval_id": raw,
            }
        else:
            raise ValueError(
                "Campaign evaluation map values must be objects or eval IDs."
            )
        evaluations.append(evaluation)
    return evaluations


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string.")
    return value


def _base_agent_name(pipeline: Any) -> str | None:
    if not isinstance(pipeline, str) or not pipeline:
        return None
    return Path(pipeline).stem or None


def _integer(value: Any, *, default: int) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def _number(value: Any, *, default: float) -> float:
    return (
        float(value)
        if isinstance(value, (int, float)) and not isinstance(value, bool)
        else default
    )
