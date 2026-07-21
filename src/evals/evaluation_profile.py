"""Project-owned evaluation profile loading, predicates, slices, and preflight."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from evaluation import GraderRegistry, JsonScalar, read_path
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
import yaml

from src.benchmarks import BenchmarkExample, BenchmarkVersion


def canonical_sha256(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class GraderConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    version: int = Field(ge=1)
    config: dict[str, Any] = Field(default_factory=dict)


class ActualFieldConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    receipt_metadata_path: tuple[str, ...] = Field(min_length=1)
    type: Literal["string", "integer", "number", "boolean", "null"]


class ConfidenceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    receipt_metadata_path: tuple[str, ...] = Field(min_length=1)
    values: tuple[JsonScalar, ...] = Field(min_length=1)


class FieldEvaluationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    benchmark_label_path: tuple[str, ...] = Field(min_length=1)
    grader: GraderConfig


class OutputFieldConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str = Field(min_length=1)
    actual: ActualFieldConfig
    presence: Literal["required", "optional"] | dict[str, Any]
    confidence: ConfidenceConfig | None = None
    evaluation: FieldEvaluationConfig | None = None

    @field_validator("presence")
    @classmethod
    def validate_presence(
        cls, value: Literal["required", "optional"] | dict[str, Any]
    ) -> Literal["required", "optional"] | dict[str, Any]:
        if isinstance(value, dict):
            if set(value) != {"conditional"}:
                raise ValueError("Conditional presence requires only 'conditional'.")
            validate_predicate(value["conditional"])
        return value


class SliceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str = Field(min_length=1)
    label: str = Field(min_length=1)
    where: dict[str, Any]

    @field_validator("where")
    @classmethod
    def validate_where(cls, value: dict[str, Any]) -> dict[str, Any]:
        validate_predicate(value)
        return value


class BenchmarkCompatibility(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_keys: tuple[str, ...] = Field(min_length=1)


class EvaluationProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1]
    profile_id: str = Field(min_length=1)
    profile_version: int = Field(ge=1)
    benchmark_compatibility: BenchmarkCompatibility
    output_fields: tuple[OutputFieldConfig, ...] = Field(min_length=1)
    slices: tuple[SliceConfig, ...] = ()

    @model_validator(mode="after")
    def validate_unique_keys(self) -> "EvaluationProfile":
        field_keys = [field.key for field in self.output_fields]
        if len(field_keys) != len(set(field_keys)):
            raise ValueError("Evaluation profile output field keys must be unique.")
        slice_keys = [item.key for item in self.slices]
        if len(slice_keys) != len(set(slice_keys)):
            raise ValueError("Evaluation profile slice keys must be unique.")
        if not any(field.evaluation is not None for field in self.output_fields):
            raise ValueError("Evaluation profile requires at least one graded field.")
        return self

    @property
    def content_sha256(self) -> str:
        return canonical_sha256(self.model_dump(mode="json"))

    @property
    def grader_set_sha256(self) -> str:
        return canonical_sha256(
            [
                field.evaluation.grader.model_dump(mode="json")
                for field in self.output_fields
                if field.evaluation is not None
            ]
        )

    @property
    def slice_definition_sha256(self) -> str:
        return canonical_sha256([item.model_dump(mode="json") for item in self.slices])


class EvaluationPreflight(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    profile: EvaluationProfile
    profile_path: str
    example_slices: dict[str, tuple[str, ...]]
    slice_counts: dict[str, int]


def load_evaluation_profile(path: str | Path) -> EvaluationProfile:
    source = Path(path)
    payload = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError("Evaluation profile YAML must define a mapping.")
    return EvaluationProfile.model_validate(payload)


def preflight_evaluation(
    *,
    profile: EvaluationProfile,
    profile_path: str | Path,
    benchmark: BenchmarkVersion,
    examples: list[BenchmarkExample],
    grader_registry: GraderRegistry,
    agent_output_schema: dict[str, Any],
) -> EvaluationPreflight:
    allowed_schema_keys = set(profile.benchmark_compatibility.schema_keys)
    schemas = {schema.schema_version_id: schema for schema in benchmark.label_schemas}
    used_schema_keys: set[str] = set()
    for example in examples:
        schema = schemas.get(example.label_schema_version_id)
        if schema is None:
            raise ValueError(
                f"Example {example.example_id} references an unavailable label schema."
            )
        used_schema_keys.add(schema.schema_key)
        _validate_published_label_payload(
            example.approved_label_payload,
            schema.schema_document,
            example_id=example.example_id,
        )
    unsupported = used_schema_keys - allowed_schema_keys
    if unsupported:
        raise ValueError(
            "Evaluation profile does not support benchmark label schemas: "
            + ", ".join(sorted(unsupported))
        )

    _validate_receipt_paths(profile, agent_output_schema=agent_output_schema)

    for field in profile.output_fields:
        if field.evaluation is None:
            continue
        grader = field.evaluation.grader
        resolved = grader_registry.resolve(grader.id, grader.version)
        _validate_grader_config(resolved, field.actual.type, grader.config)

    example_slices = {
        example.example_id: slice_memberships(example, profile) for example in examples
    }
    slice_counts = {
        item.key: sum(
            item.key in memberships for memberships in example_slices.values()
        )
        for item in profile.slices
    }

    for example in examples:
        context = evaluation_context(example=example, agent_outputs={})
        for field in profile.output_fields:
            if field.evaluation is None or not field_is_applicable(field, context):
                continue
            found, value = read_path(
                example.approved_label_payload,
                field.evaluation.benchmark_label_path,
            )
            if not found:
                raise ValueError(
                    f"Example {example.example_id} is missing benchmark target "
                    f"for output field {field.key!r}."
                )
            if not is_json_scalar(value):
                raise ValueError(
                    f"Benchmark target for {field.key!r} must be a JSON scalar."
                )
            if not _matches_declared_type(value, field.actual.type):
                raise ValueError(
                    f"Benchmark target for {field.key!r} in example "
                    f"{example.example_id} is incompatible with declared output "
                    f"type {field.actual.type!r}."
                )
            grader_config = field.evaluation.grader
            grader = grader_registry.resolve(
                grader_config.id,
                grader_config.version,
            )
            try:
                grader.grade(
                    expected=value,
                    actual=_sample_for_type(field.actual.type),
                    config=grader_config.config,
                )
            except ValueError as error:
                raise ValueError(
                    f"Grader {grader.grader_id}@{grader.grader_version} is "
                    f"incompatible with benchmark target {field.key!r} in example "
                    f"{example.example_id}: {error}"
                ) from error

    return EvaluationPreflight(
        profile=profile,
        profile_path=str(Path(profile_path)),
        example_slices=example_slices,
        slice_counts=slice_counts,
    )


def evaluation_context(
    *, example: BenchmarkExample, agent_outputs: dict[str, JsonScalar]
) -> dict[str, Any]:
    return {
        "benchmark": {
            "labels": example.approved_label_payload,
            "example_metadata": example.example_metadata,
            "unit_id": example.unit_id,
            "decision_timestamp": example.decision_timestamp.isoformat(),
        },
        "agent": {"outputs": agent_outputs},
    }


def field_is_applicable(field: OutputFieldConfig, context: dict[str, Any]) -> bool:
    if isinstance(field.presence, str):
        return True
    return evaluate_predicate(field.presence["conditional"], context)


def field_is_required(field: OutputFieldConfig, context: dict[str, Any]) -> bool:
    if field.presence == "required":
        return True
    if field.presence == "optional":
        return False
    return evaluate_predicate(field.presence["conditional"], context)


def slice_memberships(
    example: BenchmarkExample, profile: EvaluationProfile
) -> tuple[str, ...]:
    context = evaluation_context(example=example, agent_outputs={})
    return tuple(
        item.key for item in profile.slices if evaluate_predicate(item.where, context)
    )


def evaluate_predicate(predicate: dict[str, Any], context: dict[str, Any]) -> bool:
    validate_predicate(predicate)
    operator, payload = next(iter(predicate.items()))
    if operator in {"and", "or"}:
        outcomes = [evaluate_predicate(item, context) for item in payload]
        return all(outcomes) if operator == "and" else any(outcomes)
    if operator == "not":
        return not evaluate_predicate(payload, context)
    found, actual = read_path(context, payload["path"])
    if operator == "exists":
        return found is bool(payload["value"])
    if not found:
        return False
    if operator == "equals":
        return type(actual) is type(payload["value"]) and actual == payload["value"]
    if operator == "not_equals":
        return not (
            type(actual) is type(payload["value"]) and actual == payload["value"]
        )
    return any(
        type(actual) is type(value) and actual == value for value in payload["values"]
    )


def validate_predicate(predicate: Any) -> None:
    if not isinstance(predicate, dict) or len(predicate) != 1:
        raise ValueError("Predicate must contain exactly one operator.")
    operator, payload = next(iter(predicate.items()))
    if operator in {"and", "or"}:
        if not isinstance(payload, list) or not payload:
            raise ValueError(f"Predicate {operator!r} requires a non-empty list.")
        for child in payload:
            validate_predicate(child)
        return
    if operator == "not":
        validate_predicate(payload)
        return
    if operator not in {"equals", "not_equals", "in", "exists"}:
        raise ValueError(f"Unsupported predicate operator {operator!r}.")
    if not isinstance(payload, dict):
        raise ValueError(f"Predicate {operator!r} requires a mapping.")
    path = payload.get("path")
    if (
        not isinstance(path, (list, tuple))
        or not path
        or not all(isinstance(part, str) and part for part in path)
    ):
        raise ValueError("Predicate path must be a non-empty string list.")
    expected_keys = {"path", "values"} if operator == "in" else {"path", "value"}
    if set(payload) != expected_keys:
        raise ValueError(
            f"Predicate {operator!r} requires keys: {', '.join(sorted(expected_keys))}."
        )
    if operator == "in":
        values = payload["values"]
        if (
            not isinstance(values, list)
            or not values
            or not all(is_json_scalar(value) for value in values)
        ):
            raise ValueError("Predicate 'in' requires non-empty scalar values.")
    elif operator == "exists":
        if not isinstance(payload["value"], bool):
            raise ValueError("Predicate 'exists' value must be boolean.")
    elif not is_json_scalar(payload["value"]):
        raise ValueError(f"Predicate {operator!r} value must be a JSON scalar.")


def is_json_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _validate_receipt_paths(
    profile: EvaluationProfile,
    *,
    agent_output_schema: dict[str, Any],
) -> None:
    for field in profile.output_fields:
        actual_path = field.actual.receipt_metadata_path
        actual_schema = _agent_output_path_schema(
            agent_output_schema,
            actual_path,
            field_key=field.key,
        )
        if not _schema_accepts_type(actual_schema, field.actual.type):
            raise ValueError(
                f"Receipt path for output field {field.key!r} is incompatible "
                f"with declared type {field.actual.type!r}."
            )
        if field.confidence is None:
            continue
        confidence_schema = _agent_output_path_schema(
            agent_output_schema,
            field.confidence.receipt_metadata_path,
            field_key=f"{field.key}.confidence",
        )
        allowed = confidence_schema.get("enum")
        if isinstance(allowed, list) and any(
            value not in allowed for value in field.confidence.values
        ):
            raise ValueError(
                f"Configured confidence values for {field.key!r} are not allowed "
                "by the pipeline output schema."
            )


def _agent_output_path_schema(
    root_schema: dict[str, Any],
    receipt_path: tuple[str, ...],
    *,
    field_key: str,
) -> dict[str, Any]:
    if not receipt_path or receipt_path[0] != "agent_output":
        raise ValueError(
            f"Receipt path for {field_key!r} must begin with 'agent_output'."
        )
    current = root_schema
    for part in receipt_path[1:]:
        current = _resolve_schema_node(root_schema, current)
        properties = current.get("properties")
        if not isinstance(properties, dict) or part not in properties:
            raise ValueError(
                f"Receipt path for {field_key!r} is absent from the pipeline "
                f"output schema at {part!r}."
            )
        child = properties[part]
        if not isinstance(child, dict):
            raise ValueError(f"Pipeline output schema for {field_key!r} is invalid.")
        current = child
    return _resolve_schema_node(root_schema, current)


def _resolve_schema_node(
    root_schema: dict[str, Any], node: dict[str, Any]
) -> dict[str, Any]:
    reference = node.get("$ref")
    if not isinstance(reference, str):
        return node
    prefix = "#/$defs/"
    if not reference.startswith(prefix):
        raise ValueError(f"Unsupported pipeline output schema reference: {reference}")
    resolved = root_schema.get("$defs", {}).get(reference.removeprefix(prefix))
    if not isinstance(resolved, dict):
        raise ValueError(f"Unresolved pipeline output schema reference: {reference}")
    return resolved


def _schema_accepts_type(schema: dict[str, Any], declared_type: str) -> bool:
    raw_types: set[str] = set()
    schema_type = schema.get("type")
    if isinstance(schema_type, str):
        raw_types.add(schema_type)
    for branch in schema.get("anyOf", []):
        if isinstance(branch, dict) and isinstance(branch.get("type"), str):
            raw_types.add(branch["type"])
    accepted = {
        "string": {"string"},
        "integer": {"integer"},
        "number": {"integer", "number"},
        "boolean": {"boolean"},
        "null": {"null"},
    }[declared_type]
    return bool(raw_types & accepted)


def _matches_declared_type(value: JsonScalar, declared_type: str) -> bool:
    if declared_type == "null":
        return value is None
    if declared_type == "boolean":
        return isinstance(value, bool)
    if declared_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if declared_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return isinstance(value, str)


def _sample_for_type(value_type: str) -> JsonScalar:
    return {
        "string": "sample",
        "integer": 1,
        "number": 1.0,
        "boolean": True,
        "null": None,
    }[value_type]


def _validate_grader_config(
    grader: Any, value_type: str, config: dict[str, Any]
) -> None:
    try:
        grader.grade(
            expected=_sample_for_type(value_type),
            actual=_sample_for_type(value_type),
            config=config,
        )
    except ValueError as error:
        raise ValueError(
            f"Invalid configuration for {grader.grader_id}@{grader.grader_version}: "
            f"{error}"
        ) from error


def _validate_published_label_payload(
    payload: dict[str, Any], schema: dict[str, Any], *, example_id: str
) -> None:
    fields_raw = schema.get("fields")
    if not isinstance(fields_raw, list):
        raise ValueError("Published label schema fields must be a list.")
    fields = {
        str(field.get("key")): field
        for field in fields_raw
        if isinstance(field, dict) and str(field.get("key", "")).strip()
    }
    unknown = set(payload) - set(fields)
    if unknown:
        raise ValueError(
            f"Example {example_id} contains labels absent from its frozen schema: "
            + ", ".join(sorted(unknown))
        )
    for key, field in fields.items():
        if field.get("required") is True and key not in payload:
            raise ValueError(f"Example {example_id} is missing required label {key!r}.")
        if key not in payload:
            continue
        allowed = field.get("values")
        if isinstance(allowed, list) and payload[key] not in allowed:
            raise ValueError(
                f"Example {example_id} label {key!r} is outside its frozen schema."
            )
    rules = schema.get("rules", [])
    if not isinstance(rules, list):
        raise ValueError("Published label schema rules must be a list.")
    for rule in rules:
        if not isinstance(rule, dict):
            raise ValueError("Published label schema rules must be objects.")
        when = rule.get("when", {})
        requirement = rule.get("require", {})
        if not isinstance(when, dict) or not isinstance(requirement, dict):
            raise ValueError("Published label schema rule clauses must be objects.")
        when_field = str(when.get("field", ""))
        if payload.get(when_field) != when.get("equals"):
            continue
        required_field = str(requirement.get("field", ""))
        actual = payload.get(required_field)
        valid = (
            actual == requirement["equals"]
            if "equals" in requirement
            else actual in requirement.get("in", [])
        )
        if not valid:
            raise ValueError(
                f"Example {example_id} violates frozen label schema rule: "
                f"{rule.get('message', required_field)}"
            )
