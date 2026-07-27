"""JSON retriever with schema validation, conversion, and filtering.

Quick Start (builder-friendly):
    from mi.core.retrievers import JsonRetriever, JsonRetrieverConfig, FieldSchema

    retriever = JsonRetriever(
        JsonRetrieverConfig(
            file_path="data/devices.json",
            root_key="devices",
            filter_field="deviceId",
            fields=[FieldSchema(name="deviceId", type="str"), FieldSchema(name="siteId", type="str")],
        )
    )

YAML users can declare the same settings under ``retrieve.retrievers``; both
approaches are supported. See README.md and core/GETTING_STARTED.md for a full
walkthrough of YAML and builder usage.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd  # pyright: ignore[reportMissingImports]
from pydantic import BaseModel, Field

from mi.core.pipeline import PipelineMetadata
from mi.core.retrievers import BaseRetriever, BaseRetrieverConfig
from mi.core.utils.typing import (
    SchemaScalarType,
    apply_type_conversions,
    validate_schema,
)
from mi.utilities import cache


# Supported field types for schema definition
FieldType = SchemaScalarType


class FieldSchema(BaseModel):
    """Schema definition for a JSON field.

    Attributes:
        name: Field name as it appears in the JSON.
        type: Target data type for conversion.
        nullable: Whether the field allows null/missing values.
        datetime_format: Format string for datetime parsing.
    """

    name: str = Field(description="Field name in the JSON")
    type: FieldType = Field(default="str", description="Target data type")
    nullable: bool = Field(default=True, description="Whether nulls are allowed")
    datetime_format: str | None = Field(
        default=None, description="Datetime format string (e.g., '%Y-%m-%d %H:%M:%S')"
    )


class JsonRetrieverConfig(BaseRetrieverConfig):
    """Configuration for the JSON retriever.

    Attributes:
        file_path: Path to the JSON file.
        root_key: Key in the JSON object containing the array of records (e.g., "devices").
            If None, assumes the root is an array.
        fields: List of field schemas defining expected fields and types.
        filter_field: Field name to filter on using pipeline metadata unit value.
        encoding: File encoding.
        strict: If True, fail on schema mismatch; if False, log warnings and continue.
    """

    name: str = Field(default="json", description="Name of the retriever")

    file_path: str = Field(description="Path to the JSON file")
    root_key: str | None = Field(
        default=None,
        description="Key containing the array of records (None if root is array)",
    )
    fields: list[FieldSchema] = Field(
        default_factory=list, description="Field schema definitions"
    )
    filter_field: str | None = Field(
        default=None,
        description="Field to filter on using metadata.unit value",
    )
    encoding: str = Field(default="utf-8", description="File encoding")
    strict: bool = Field(default=False, description="Fail on schema mismatch if True")


class JsonRetriever(BaseRetriever):
    """Retriever that reads JSON files with schema validation and type conversion.

    This retriever reads a JSON file, extracts records from a specified root key,
    validates the structure against a defined schema, converts fields to the
    specified types, and optionally filters by :class:`PipelineMetadata`.
    """

    def __init__(self, config: JsonRetrieverConfig) -> None:
        """Initialize the JSON retriever.

        Args:
            config: Configuration specifying file path, schema, and parsing options.
        """
        super().__init__(config)

        self._file_path = Path(config.file_path).expanduser().resolve()
        self._root_key = config.root_key
        self._fields = {field.name: field for field in config.fields}
        self._filter_field = config.filter_field
        self._encoding = config.encoding
        self._strict = config.strict

    def retrieve(self, *, metadata: PipelineMetadata | None = None) -> pd.DataFrame:
        """Retrieve and parse the JSON file with type conversion.

        Args:
            metadata: Optional pipeline metadata. Defaults to None.

        Returns:
            DataFrame-like object with typed fields. Uses pandas when available,
            otherwise Polars if installed, else returns a list of dictionaries.

        Raises:
            FileNotFoundError: If the JSON file does not exist.
            ValueError: In strict mode, if schema validation fails.
        """
        if not self._file_path.exists():
            message = f"JSON file not found: {self._file_path}"
            if self._strict:
                raise FileNotFoundError(message)
            self.logger.warning(message)
            return pd.DataFrame()

        data = self._read_json()
        records = self._extract_records(data)

        if not records:
            self.logger.warning("No records found in JSON file")
            return pd.DataFrame()

        return self._retrieve_with_pandas(records, metadata)

    def _read_json(self) -> Any:
        """Read the JSON file, leveraging the shared cache to avoid repeated IO.

        Returns:
            Parsed JSON data.
        """

        @cache(log_misses=True)
        def _load_json(path: Path) -> Any:
            return json.loads(path.read_text(encoding=self._encoding))

        return _load_json(self._file_path)

    def _extract_records(self, data: Any) -> list[dict[str, Any]]:
        """Extract records from the JSON data.

        Args:
            data: Parsed JSON data.

        Returns:
            List of record dictionaries.

        Raises:
            ValueError: If root_key is specified but not found, or data is not an array.
        """
        if self._root_key:
            if not isinstance(data, dict):
                message = f"Expected JSON object with key '{self._root_key}', got {type(data).__name__}"
                if self._strict:
                    raise ValueError(message)
                self.logger.warning(message)
                return []

            if self._root_key not in data:
                message = f"Root key '{self._root_key}' not found in JSON"
                if self._strict:
                    raise ValueError(message)
                self.logger.warning(message)
                return []

            records = data[self._root_key]
        else:
            records = data

        if not isinstance(records, list):
            message = f"Expected array of records, got {type(records).__name__}"
            if self._strict:
                raise ValueError(message)
            self.logger.warning(message)
            return []

        return records

    def _retrieve_with_pandas(
        self, records: list[dict[str, Any]], metadata: PipelineMetadata | None
    ) -> pd.DataFrame:
        """Retrieve using pandas backend.

        Converts raw records into a DataFrame, validates schema, applies type
        conversions, filters by metadata, and logs record counts.
        """
        df = pd.DataFrame(records)
        validate_schema(
            df,
            self._fields,
            strict=self._strict,
            logger=self.logger,
            context="JSON",
        )
        df = apply_type_conversions(
            df,
            self._fields,
            strict=self._strict,
            logger=self.logger,
        )
        df = self._apply_metadata_filter(df, metadata)

        self.logger.info("Retrieved %d records from %s", len(df), self._file_path.name)
        return df

    def _apply_metadata_filter(
        self, df: pd.DataFrame, metadata: PipelineMetadata | None
    ) -> pd.DataFrame:
        """Filter DataFrame rows based on pipeline metadata.

        Applies ``metadata.unit`` against ``filter_field`` when configured;
        logs and returns the unfiltered frame when metadata is absent or the
        column is missing.
        """
        if not self._filter_field:
            return df

        if not metadata:
            self.logger.warning(
                "Filter field '%s' configured but no metadata provided, skipping filter",
                self._filter_field,
            )
            return df

        if self._filter_field not in df.columns:
            message = f"Filter field '{self._filter_field}' not found in JSON"
            if self._strict:
                raise ValueError(message)
            self.logger.warning(message)
            return df

        filter_value = metadata.unit
        original_count = len(df)

        col_dtype = df[self._filter_field].dtype
        if pd.api.types.is_numeric_dtype(col_dtype):
            try:
                filter_value = type(df[self._filter_field].iloc[0])(filter_value)
            except (ValueError, TypeError, IndexError):
                pass

        df = df.loc[df[self._filter_field] == filter_value].copy()
        filtered_count = len(df)

        self.logger.info(
            "Filtered %s=%s: %d -> %d records",
            self._filter_field,
            filter_value,
            original_count,
            filtered_count,
        )

        return df
