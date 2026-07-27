"""Versioned deterministic graders for JSON scalar agent outputs."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
import math
import re
from typing import Any, Protocol

from evaluation.models import JsonScalar


@dataclass(frozen=True, slots=True)
class FieldGrade:
    correct: bool
    expected: JsonScalar
    actual: JsonScalar
    normalized_expected: JsonScalar = None
    normalized_actual: JsonScalar = None
    details: dict[str, Any] = field(default_factory=dict)


class DeterministicGrader(Protocol):
    grader_id: str
    grader_version: int

    def grade(
        self,
        *,
        expected: JsonScalar,
        actual: JsonScalar,
        config: Mapping[str, Any],
    ) -> FieldGrade: ...


GraderFactory = Callable[[], DeterministicGrader]


class GraderRegistry:
    """Explicit registry; evaluation YAML never imports arbitrary code."""

    def __init__(self) -> None:
        self._factories: dict[tuple[str, int], GraderFactory] = {}

    def register(self, factory: GraderFactory) -> None:
        grader = factory()
        identity = (grader.grader_id, grader.grader_version)
        if not grader.grader_id.strip() or grader.grader_version < 1:
            raise ValueError("Grader identity must have a name and positive version.")
        if identity in self._factories:
            raise ValueError(f"Duplicate grader registration: {identity!r}.")
        self._factories[identity] = factory

    def resolve(self, grader_id: str, grader_version: int) -> DeterministicGrader:
        factory = self._factories.get((grader_id, grader_version))
        if factory is None:
            raise ValueError(
                f"Unknown deterministic grader {grader_id}@{grader_version}."
            )
        return factory()

    def identities(self) -> tuple[tuple[str, int], ...]:
        return tuple(sorted(self._factories))


class ExactGrader:
    grader_id = "core.exact"
    grader_version = 1

    def grade(
        self,
        *,
        expected: JsonScalar,
        actual: JsonScalar,
        config: Mapping[str, Any],
    ) -> FieldGrade:
        if config:
            raise ValueError("core.exact does not accept configuration.")
        correct = type(expected) is type(actual) and expected == actual
        return FieldGrade(correct=correct, expected=expected, actual=actual)


class NormalizedStringGrader:
    grader_id = "core.normalized_string"
    grader_version = 1

    _OPTIONS = {"trim", "casefold", "collapse_whitespace", "aliases"}

    def grade(
        self,
        *,
        expected: JsonScalar,
        actual: JsonScalar,
        config: Mapping[str, Any],
    ) -> FieldGrade:
        unknown = set(config) - self._OPTIONS
        if unknown:
            raise ValueError(
                "Unsupported normalized-string options: " + ", ".join(sorted(unknown))
            )
        if not isinstance(expected, str) or not isinstance(actual, str):
            raise ValueError("core.normalized_string requires string values.")
        aliases_raw = config.get("aliases", {})
        if not isinstance(aliases_raw, Mapping) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in aliases_raw.items()
        ):
            raise ValueError("normalized-string aliases must map strings to strings.")

        def normalize(value: str) -> str:
            normalized = value.strip() if config.get("trim", False) else value
            if config.get("collapse_whitespace", False):
                normalized = re.sub(r"\s+", " ", normalized)
            if config.get("casefold", False):
                normalized = normalized.casefold()
            return aliases_raw.get(normalized, normalized)

        normalized_expected = normalize(expected)
        normalized_actual = normalize(actual)
        return FieldGrade(
            correct=normalized_expected == normalized_actual,
            expected=expected,
            actual=actual,
            normalized_expected=normalized_expected,
            normalized_actual=normalized_actual,
        )


class NumericToleranceGrader:
    grader_id = "core.numeric_tolerance"
    grader_version = 1

    def grade(
        self,
        *,
        expected: JsonScalar,
        actual: JsonScalar,
        config: Mapping[str, Any],
    ) -> FieldGrade:
        unknown = set(config) - {"absolute", "relative"}
        if unknown:
            raise ValueError(
                "Unsupported numeric-tolerance options: " + ", ".join(sorted(unknown))
            )
        if isinstance(expected, bool) or isinstance(actual, bool):
            raise ValueError("core.numeric_tolerance does not accept booleans.")
        if not isinstance(expected, (int, float)) or not isinstance(
            actual, (int, float)
        ):
            raise ValueError("core.numeric_tolerance requires numeric values.")
        absolute = config.get("absolute")
        relative = config.get("relative")
        if absolute is None and relative is None:
            raise ValueError("numeric tolerance requires absolute and/or relative.")
        for name, value in (("absolute", absolute), ("relative", relative)):
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or value < 0
            ):
                raise ValueError(f"{name} tolerance must be a non-negative number.")
        correct = math.isclose(
            float(actual),
            float(expected),
            rel_tol=float(relative or 0.0),
            abs_tol=float(absolute or 0.0),
        )
        return FieldGrade(
            correct=correct,
            expected=expected,
            actual=actual,
            details={"absolute_tolerance": absolute, "relative_tolerance": relative},
        )


def build_default_grader_registry() -> GraderRegistry:
    registry = GraderRegistry()
    registry.register(ExactGrader)
    registry.register(NormalizedStringGrader)
    registry.register(NumericToleranceGrader)
    return registry
