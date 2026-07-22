"""Validated preflight manifests and paired schema-v3 evaluation comparisons."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from typing import Any

from evaluation import build_comparison_identity

from src.evals.result_integrity import load_verified_result


def build_comparison_manifest(
    manifest_paths: list[Path],
    *,
    varying_dimensions: set[str],
    output_dir: Path | None = None,
) -> Path:
    """Validate every child plan and persist comparison identity pre-execution."""
    if len(manifest_paths) < 2:
        raise ValueError("A comparison requires at least two run manifests.")
    manifests = [_load_object(path) for path in manifest_paths]
    run_ids = _validated_run_ids(manifests, config_key=None)
    dimensions = [_manifest_dimensions(item) for item in manifests]
    differing, warnings = _validate_dimensions(dimensions, varying_dimensions)
    scopes = [tuple(item["run_spec"]["scope"]["example_ids"]) for item in manifests]
    if len(set(scopes)) != 1:
        raise ValueError("Comparison runs must select the same ordered example IDs.")
    repetitions = [int(item["run_spec"]["runs_per_example"]) for item in manifests]
    if len(set(repetitions)) != 1:
        raise ValueError("Comparison runs must use the same repetition count.")
    spec = _comparison_spec(
        run_ids=run_ids,
        varying_dimensions=varying_dimensions,
        dimensions=dimensions,
        differing=differing,
        selected=scopes[0],
        repetitions=repetitions[0],
    )
    comparison_id, digest = build_comparison_identity(spec)
    payload = {
        "comparison_id": comparison_id,
        "comparison_spec_sha256": digest,
        "comparison_spec": spec,
        "warnings": warnings,
        "child_manifests": [str(path) for path in manifest_paths],
    }
    target_dir = output_dir or manifest_paths[0].parents[2] / "comparisons"
    return _write_immutable(target_dir / f"{comparison_id}.manifest.json", payload)


def build_comparison(
    result_paths: list[Path],
    *,
    varying_dimensions: set[str],
    output_dir: Path | None = None,
    comparison_manifest_path: Path | None = None,
) -> Path:
    """Compare aligned runs while rejecting undeclared configuration changes."""
    if len(result_paths) < 2:
        raise ValueError("A comparison requires at least two result files.")
    results = [load_verified_result(path) for path in result_paths]
    manifests = [_load_object(path.parent / "manifest.json") for path in result_paths]
    run_ids = _validated_run_ids(results, config_key="run_config")
    dimensions = [_manifest_dimensions(item) for item in manifests]
    differing, warnings = _validate_dimensions(dimensions, varying_dimensions)
    selected = [tuple(item["selected_example_ids"]) for item in results]
    if len(set(selected)) != 1:
        raise ValueError("Comparison runs must select the same ordered example IDs.")
    repetitions = [int(item["run_config"]["runs_per_example"]) for item in results]
    if len(set(repetitions)) != 1:
        raise ValueError("Comparison runs must use the same repetition count.")

    if comparison_manifest_path is None:
        spec = _comparison_spec(
            run_ids=run_ids,
            varying_dimensions=varying_dimensions,
            dimensions=dimensions,
            differing=differing,
            selected=selected[0],
            repetitions=repetitions[0],
        )
        comparison_id, digest = build_comparison_identity(spec)
    else:
        manifest = _load_object(comparison_manifest_path)
        spec = manifest.get("comparison_spec")
        if not isinstance(spec, dict) or spec.get("run_ids") != run_ids:
            raise ValueError(
                "Comparison results do not match the preflight child runs."
            )
        if spec.get("varying_dimensions") != sorted(varying_dimensions):
            raise ValueError("Comparison varying dimensions differ from preflight.")
        comparison_id = str(manifest.get("comparison_id", ""))
        digest = str(manifest.get("comparison_spec_sha256", ""))
        expected_id, expected_digest = build_comparison_identity(spec)
        if (comparison_id, digest) != (expected_id, expected_digest):
            raise ValueError("Comparison preflight manifest identity is invalid.")

    payload = {
        "comparison_id": comparison_id,
        "comparison_spec_sha256": digest,
        "comparison_spec": spec,
        "warnings": warnings,
        "runs": [
            _comparison_row(result, path=path)
            for result, path in zip(results, result_paths, strict=True)
        ],
        "paired_complete_correctness": _multi_run_agreement(results),
        "paired_deltas": [
            _paired_delta(results[0], candidate) for candidate in results[1:]
        ],
    }
    target_dir = output_dir or result_paths[0].parents[2] / "comparisons"
    return _write_immutable(target_dir / f"{comparison_id}.json", payload)


def _comparison_spec(
    *,
    run_ids: list[str],
    varying_dimensions: set[str],
    dimensions: list[dict[str, Any]],
    differing: set[str],
    selected: tuple[str, ...],
    repetitions: int,
) -> dict[str, Any]:
    all_keys = sorted(set().union(*(set(item) for item in dimensions)))
    return {
        "comparison_schema_version": 1,
        "run_ids": run_ids,
        "varying_dimensions": sorted(varying_dimensions),
        "invariant_dimensions": {
            key: dimensions[0].get(key) for key in all_keys if key not in differing
        },
        "aligned_example_ids": list(selected),
        "runs_per_example": repetitions,
    }


def _manifest_dimensions(payload: dict[str, Any]) -> dict[str, Any]:
    spec = payload.get("run_spec")
    if not isinstance(spec, dict):
        raise ValueError("Run manifest is missing run_spec.")
    # Derived hashes that include the model are represented by the model itself;
    # retaining them separately would turn one declared model change into several.
    pipeline = spec.get("pipeline", {})
    execution = spec.get("execution", {})
    semantic = {
        "benchmark": spec.get("benchmark"),
        "scope": spec.get("scope"),
        "pipeline": {
            key: value
            for key, value in pipeline.items()
            if key != "resolved_override_sha256"
        },
        "agent": spec.get("agent"),
        "model": {
            **(spec.get("model") or {}),
            "execution_policies": _execution_policies_without_model(
                execution.get("ai_execution_policies")
            ),
        },
        "scoring": spec.get("scoring"),
        "execution": {
            key: value
            for key, value in execution.items()
            if key != "ai_execution_policies"
        },
        "configuration": spec.get("configuration_dimensions"),
        "source": spec.get("source_manifest"),
    }
    return _flatten(semantic)


def _execution_policies_without_model(value: Any) -> Any:
    """Keep retry/timeout policy dimensions without duplicating model identity."""
    if not isinstance(value, list):
        return value
    return [
        {
            key: item_value
            for key, item_value in item.items()
            if key not in {"model", "reasoning_effort"}
        }
        if isinstance(item, dict)
        else item
        for item in value
    ]


def _validated_run_ids(
    payloads: list[dict[str, Any]], *, config_key: str | None
) -> list[str]:
    run_ids = [
        str(
            (item if config_key is None else item.get(config_key, {})).get("run_id", "")
        )
        for item in payloads
    ]
    if any(not item for item in run_ids):
        raise ValueError("Only deterministic schema-v3 runs can be compared.")
    if len(set(run_ids)) != len(run_ids):
        raise ValueError("A comparison cannot contain the same run more than once.")
    return run_ids


def _validate_dimensions(
    dimensions: list[dict[str, Any]], varying: set[str]
) -> tuple[set[str], list[str]]:
    keys = sorted(set().union(*(set(item) for item in dimensions)))
    differing = {
        key
        for key in keys
        if len({_json_key(item.get(key)) for item in dimensions}) > 1
    }
    undeclared = {
        key
        for key in differing
        if not any(
            key == allowed or key.startswith(f"{allowed}.") for allowed in varying
        )
    }
    if undeclared:
        raise ValueError(
            "Comparison runs differ in undeclared dimensions: "
            + ", ".join(sorted(undeclared))
        )
    constant = {
        allowed
        for allowed in varying
        if not any(key == allowed or key.startswith(f"{allowed}.") for key in differing)
    }
    warnings = (
        ["Declared varying dimensions were constant: " + ", ".join(sorted(constant))]
        if constant
        else []
    )
    return differing, warnings


def _comparison_row(payload: dict[str, Any], *, path: Path) -> dict[str, Any]:
    summary = payload["summary"]
    return {
        "run_id": payload["run_config"]["run_id"],
        "result_path": str(path),
        "dimensions": payload["run_config"].get("dimensions", {}),
        "complete_evaluation": summary["accuracy"]["complete_evaluation"],
        "reliability": summary["reliability"],
        "scoring_coverage": summary["scoring_coverage"],
        "performance": summary["performance"],
        "usage": summary.get("usage"),
        "retries": summary.get("retries"),
        "cost": summary.get("cost"),
        "nondeterminism": summary.get("nondeterminism"),
    }


def _work_items(payload: dict[str, Any]) -> dict[tuple[str, int], dict[str, Any]]:
    output: dict[tuple[str, int], dict[str, Any]] = {}
    for example in payload["results"]:
        for run in example["runs"]:
            output[(str(example["example_id"]), int(run["run_index"]))] = {
                **run,
                "slice_keys": tuple(example.get("slice_keys", ())),
            }
    return output


def _multi_run_agreement(results: list[dict[str, Any]]) -> dict[str, Any]:
    observations = [_work_items(item) for item in results]
    shared = set.intersection(*(set(item) for item in observations))
    scorable = [
        key
        for key in sorted(shared)
        if all(
            item[key].get("complete_evaluation_correct") is not None
            for item in observations
        )
    ]
    unanimous = sum(
        len({bool(item[key]["complete_evaluation_correct"]) for item in observations})
        == 1
        for key in scorable
    )
    return {
        "aligned_work_items": len(shared),
        "jointly_scorable_work_items": len(scorable),
        "unanimous_work_items": unanimous,
        "disagreement_work_items": len(scorable) - unanimous,
        "agreement_rate": None if not scorable else unanimous / len(scorable),
    }


def _paired_delta(
    baseline: dict[str, Any], candidate: dict[str, Any]
) -> dict[str, Any]:
    left = _work_items(baseline)
    right = _work_items(candidate)
    shared = sorted(set(left).intersection(right))
    fields = sorted(
        {
            key
            for item in (*left.values(), *right.values())
            for key in item.get("fields", {})
        }
    )
    slices = sorted(
        {
            key
            for item in (*left.values(), *right.values())
            for key in item["slice_keys"]
        }
    )
    return {
        "baseline_run_id": baseline["run_config"]["run_id"],
        "candidate_run_id": candidate["run_config"]["run_id"],
        "aligned_work_items": len(shared),
        "complete_evaluation": _boolean_delta(
            [left[key].get("complete_evaluation_correct") for key in shared],
            [right[key].get("complete_evaluation_correct") for key in shared],
        ),
        "by_field": {
            field: _boolean_delta(
                [
                    left[key].get("fields", {}).get(field, {}).get("correct")
                    for key in shared
                ],
                [
                    right[key].get("fields", {}).get(field, {}).get("correct")
                    for key in shared
                ],
            )
            for field in fields
        },
        "by_slice": {
            slice_key: _boolean_delta(
                [
                    left[key].get("complete_evaluation_correct")
                    for key in shared
                    if slice_key in left[key]["slice_keys"]
                    and slice_key in right[key]["slice_keys"]
                ],
                [
                    right[key].get("complete_evaluation_correct")
                    for key in shared
                    if slice_key in left[key]["slice_keys"]
                    and slice_key in right[key]["slice_keys"]
                ],
            )
            for slice_key in slices
        },
        "reliability": {
            "execution_success": _boolean_delta(
                [left[key].get("execution_status") == "completed" for key in shared],
                [right[key].get("execution_status") == "completed" for key in shared],
            ),
            "output_contract_valid": _boolean_delta(
                [left[key].get("output_contract_status") == "valid" for key in shared],
                [right[key].get("output_contract_status") == "valid" for key in shared],
            ),
            "scored": _boolean_delta(
                [left[key].get("scoring_status") == "scored" for key in shared],
                [right[key].get("scoring_status") == "scored" for key in shared],
            ),
        },
        "performance": _numeric_observation_deltas(
            left, right, shared, "duration_seconds"
        ),
        "usage": _nested_numeric_deltas(left, right, shared, "usage"),
        "cost": _paired_cost_deltas(left, right, shared),
        "work_items": _paired_work_item_changes(left, right, shared),
    }


def _paired_work_item_changes(
    left: dict[tuple[str, int], dict[str, Any]],
    right: dict[tuple[str, int], dict[str, Any]],
    shared: list[tuple[str, int]],
) -> dict[str, list[dict[str, Any]]]:
    """List exact aligned identities behind paired aggregate changes."""
    output: dict[str, list[dict[str, Any]]] = {
        "improved": [],
        "regressed": [],
        "changed_incorrect": [],
        "newly_failed": [],
        "recovered": [],
        "output_disagreement": [],
    }
    for example_id, run_index in shared:
        baseline = left[(example_id, run_index)]
        candidate = right[(example_id, run_index)]
        baseline_correct = baseline.get("complete_evaluation_correct")
        candidate_correct = candidate.get("complete_evaluation_correct")
        baseline_healthy = baseline.get("execution_status") == "completed"
        candidate_healthy = candidate.get("execution_status") == "completed"
        identity = {
            "example_id": example_id,
            "run_index": run_index,
            "baseline_work_item_id": baseline.get("work_item_id"),
            "candidate_work_item_id": candidate.get("work_item_id"),
            "baseline_execution_id": baseline.get("execution_id"),
            "candidate_execution_id": candidate.get("execution_id"),
        }
        if baseline_correct is False and candidate_correct is True:
            output["improved"].append(identity)
        if baseline_correct is True and candidate_correct is False:
            output["regressed"].append(identity)
        if (
            baseline_correct is False
            and candidate_correct is False
            and _json_key(baseline.get("actual_outputs"))
            != _json_key(candidate.get("actual_outputs"))
        ):
            output["changed_incorrect"].append(identity)
        if baseline_healthy and not candidate_healthy:
            output["newly_failed"].append(identity)
        if not baseline_healthy and candidate_healthy:
            output["recovered"].append(identity)
        if _json_key(baseline.get("actual_outputs")) != _json_key(
            candidate.get("actual_outputs")
        ):
            output["output_disagreement"].append(identity)
    return output


def _boolean_delta(left: list[Any], right: list[Any]) -> dict[str, Any]:
    pairs = [
        (a, b)
        for a, b in zip(left, right, strict=True)
        if isinstance(a, bool) and isinstance(b, bool)
    ]
    baseline_correct = sum(a for a, _ in pairs)
    candidate_correct = sum(b for _, b in pairs)
    denominator = len(pairs)
    return {
        "jointly_observed": denominator,
        "baseline_positive": baseline_correct,
        "candidate_positive": candidate_correct,
        "improved": sum(not a and b for a, b in pairs),
        "regressed": sum(a and not b for a, b in pairs),
        "unchanged": sum(a == b for a, b in pairs),
        "delta_rate": None
        if denominator == 0
        else (candidate_correct - baseline_correct) / denominator,
    }


def _numeric_observation_deltas(
    left: dict[tuple[str, int], dict[str, Any]],
    right: dict[tuple[str, int], dict[str, Any]],
    shared: list[tuple[str, int]],
    key: str,
) -> dict[str, Any]:
    pairs = [
        (left[item].get(key), right[item].get(key))
        for item in shared
        if _number(left[item].get(key)) and _number(right[item].get(key))
    ]
    return _numeric_delta(pairs)


def _nested_numeric_deltas(
    left: dict[tuple[str, int], dict[str, Any]],
    right: dict[tuple[str, int], dict[str, Any]],
    shared: list[tuple[str, int]],
    key: str,
) -> dict[str, Any]:
    names = sorted(
        {
            name
            for item in shared
            for payload in (left[item].get(key), right[item].get(key))
            if isinstance(payload, dict)
            for name, value in payload.items()
            if _number(value)
        }
    )
    return {
        name: _numeric_delta(
            [
                (left[item][key][name], right[item][key][name])
                for item in shared
                if isinstance(left[item].get(key), dict)
                and isinstance(right[item].get(key), dict)
                and _number(left[item][key].get(name))
                and _number(right[item][key].get(name))
            ]
        )
        for name in names
    }


def _paired_cost_deltas(
    left: dict[tuple[str, int], dict[str, Any]],
    right: dict[tuple[str, int], dict[str, Any]],
    shared: list[tuple[str, int]],
) -> dict[str, Any]:
    currencies = sorted(
        {
            str(value["currency"])
            for item in shared
            for cost in (left[item].get("cost"), right[item].get("cost"))
            if isinstance(cost, dict)
            for field in ("actual", "estimated")
            if isinstance((value := cost.get(field)), dict)
            and _number(value.get("amount"))
            and isinstance(value.get("currency"), str)
        }
    )
    output: dict[str, Any] = {}
    for currency in currencies:
        pairs: list[tuple[float, float]] = []
        for item in shared:
            amounts = [
                _cost_amount(payload.get("cost"), currency)
                for payload in (left[item], right[item])
            ]
            baseline_amount, candidate_amount = amounts
            if baseline_amount is not None and candidate_amount is not None:
                pairs.append((baseline_amount, candidate_amount))
        output[currency] = _numeric_delta(pairs)
    return output


def _cost_amount(cost: Any, currency: str) -> float | None:
    if not isinstance(cost, dict):
        return None
    for field in ("actual", "estimated"):
        value = cost.get(field)
        if (
            isinstance(value, dict)
            and value.get("currency") == currency
            and _number(value.get("amount"))
        ):
            return float(value["amount"])
    return None


def _numeric_delta(pairs: list[tuple[Any, Any]]) -> dict[str, Any]:
    count = len(pairs)
    baseline = sum(float(a) for a, _ in pairs)
    candidate = sum(float(b) for _, b in pairs)
    return {
        "jointly_observed": count,
        "baseline_total": baseline if count else None,
        "candidate_total": candidate if count else None,
        "delta_total": candidate - baseline if count else None,
        "delta_mean": (candidate - baseline) / count if count else None,
    }


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _flatten(payload: Any, *, prefix: str = "") -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {prefix: payload}
    output: dict[str, Any] = {}
    for key, value in sorted(payload.items()):
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            output.update(_flatten(value, prefix=path))
        else:
            output[path] = value
    return output


def _json_key(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _load_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return payload


def _write_immutable(path: Path, payload: dict[str, Any]) -> Path:
    if path.exists():
        if _load_object(path) != payload:
            raise RuntimeError(f"Conflicting deterministic comparison: {path}")
        return path
    _write_json_create(path, payload)
    return path


def _write_json_create(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as temporary_file:
        json.dump(payload, temporary_file, indent=2, ensure_ascii=False)
        temporary_file.write("\n")
        temporary_file.flush()
        os.fsync(temporary_file.fileno())
        temporary_path = Path(temporary_file.name)
    try:
        os.link(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)
