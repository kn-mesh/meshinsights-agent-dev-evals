"""Schema-aware typing helpers used by CSV/JSON retrievers.

These utilities keep column handling consistent across retrievers by validating
schema definitions and performing type coercion in a pandas-first way.

Quick Start:
    import pandas as pd
    from mi.core.utils.typing import ColumnType, validate_schema, apply_type_conversions

    df = pd.DataFrame({\"value\": [\"1\", \"2\"]})
    schema = {\"value\": type(\"Col\", (), {\"type\": \"int\", \"nullable\": False})()}
    validate_schema(df, schema, strict=False, logger=print, context=\"demo\")
    df = apply_type_conversions(df, schema, strict=False, logger=print)
"""

from __future__ import annotations

from typing import Any, Literal, Mapping

import pandas as pd  # pyright: ignore[reportMissingImports]

SchemaScalarType = Literal["str", "int", "float", "bool", "datetime", "any"]


def parse_bool_value(value: Any) -> bool | None:
    """Convert common truthy/falsey strings and numbers into ``bool``.

    Returns ``None`` for missing/unknown values instead of raising so callers
    can decide whether ``None`` is acceptable for the field.
    """
    if value is None:
        return None

    if pd.isna(value):
        return None

    if isinstance(value, bool):
        return value

    str_value = str(value).lower().strip()

    if str_value in ("true", "1", "yes", "y", "on"):
        return True
    if str_value in ("false", "0", "no", "n", "off"):
        return False

    return None


def validate_schema(
    df: pd.DataFrame,
    schema: Mapping[str, Any],
    *,
    strict: bool,
    logger: Any,
    context: str,
) -> None:
    """Validate pandas DataFrame columns against a schema mapping.

    Logs missing/extra columns for observability; raises ``ValueError`` when
    ``strict`` is ``True`` and required columns are absent.
    """
    if not schema:
        logger.debug("No schema defined for %s, skipping validation", context)
        return

    expected = set(schema.keys())
    actual = set(df.columns)
    missing = expected - actual
    extra = actual - expected

    if missing:
        message = f"Missing columns in {context}: {missing}"
        if strict:
            raise ValueError(message)
        logger.warning(message)

    if extra:
        logger.debug("Extra columns in %s not in schema: %s", context, extra)


def apply_type_conversions(
    df: pd.DataFrame,
    schema: Mapping[str, Any],
    *,
    strict: bool,
    logger: Any,
) -> pd.DataFrame:
    """Apply pandas-based type conversions based on a schema mapping.

    Each schema entry must expose ``type`` and ``nullable`` attributes. Unknown
    columns are skipped; conversion errors trigger warnings or ``ValueError``
    depending on ``strict``.
    """
    if not schema:
        return df

    for name, column in schema.items():
        if name not in df.columns:
            continue

        try:
            match column.type:  # type: ignore[attr-defined]
                case "str":
                    df[name] = df[name].astype(str)
                case "int":
                    df[name] = pd.to_numeric(df[name], errors="coerce")
                    if not column.nullable:  # type: ignore[attr-defined]
                        df[name] = df[name].fillna(0).astype(int)
                case "float":
                    df[name] = pd.to_numeric(df[name], errors="coerce")
                case "bool":
                    df[name] = df[name].map(parse_bool_value)
                case "datetime":
                    df[name] = pd.to_datetime(
                        df[name],
                        format=getattr(column, "datetime_format", None),
                        errors="coerce",
                    )
                case "any":
                    pass
                case _:
                    logger.warning(
                        "Unknown dtype '%s' for column '%s', keeping as-is",
                        column.type,  # type: ignore[attr-defined]
                        name,
                    )

            null_count = int(df[name].isna().sum())
            if not column.nullable and null_count > 0:  # type: ignore[attr-defined]
                message = (
                    f"Column '{name}' has {null_count} null values but is not nullable"
                )
                if strict:
                    raise ValueError(message)
                logger.warning(message)

        except Exception as exc:
            message = f"Failed to convert column '{name}' to {column.type}: {exc}"  # type: ignore[attr-defined]
            if strict:
                raise ValueError(message) from exc
            logger.warning(message)

    return df


__all__ = [
    "SchemaScalarType",
    "validate_schema",
    "apply_type_conversions",
]
