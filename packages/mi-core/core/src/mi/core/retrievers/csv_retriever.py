"""Typed CSV retriever with schema validation, conversion, and filtering.

Reads a CSV file, applies schema-driven type coercion, optionally filters rows
using pipeline metadata, and caches parsed data for the life of the process.

Quick Start (builder-friendly):
    from mi.core.retrievers import CsvRetriever, CsvRetrieverConfig, ColumnSchema

    retriever = CsvRetriever(
        CsvRetrieverConfig(
            file_path="data/customers.csv",
            scope="default",
            filter_column="tenant_id",
            columns=[
                ColumnSchema(name="customer_id", type="str"),
                ColumnSchema(name="tenant_id", type="str"),
                ColumnSchema(name="created_at", type="datetime", datetime_format="%Y-%m-%dT%H:%M:%S"),
            ],
        )
    )

YAML users can declare the same settings under ``retrieve.retrievers``; both
approaches are supported. See README.md and core/GETTING_STARTED.md for a full
walkthrough of YAML and builder usage.
"""

from __future__ import annotations

from pathlib import Path
import time

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
from mi.core.utils.telemetry import get_tracer, ATTR_COMPONENT_LAYER

_tracer = get_tracer("retriever.csv", use_library_resource=True)


# Supported column types for schema definition
ColumnType = SchemaScalarType


class ColumnSchema(BaseModel):
    """Schema definition for a single CSV column.

    Attributes:
        name: Column name as it appears in the CSV header.
        type: Target data type for conversion.
        nullable: Whether the column allows null/missing values.
        datetime_format: Format string for datetime parsing (only used when dtype is datetime).
    """

    name: str = Field(description="Column name in the CSV")
    type: ColumnType = Field(default="str", description="Target data type")
    nullable: bool = Field(default=True, description="Whether nulls are allowed")
    datetime_format: str | None = Field(
        default=None, description="Datetime format string (e.g., '%Y-%m-%d %H:%M:%S')"
    )


class CsvRetrieverConfig(BaseRetrieverConfig):
    """Configuration for the typed CSV retriever.

    Attributes:
        file_path: Path to the CSV file.
        columns: List of column schemas defining expected columns and types.
        filter_column: Column name to filter on using pipeline metadata unit value.
        delimiter: CSV delimiter character.
        encoding: File encoding.
        skip_rows: Number of rows to skip before header.
        strict: If True, fail on schema mismatch; if False, log warnings and continue.
    """

    name: str = Field(default="csv", description="Name of the retriever")

    file_path: str = Field(description="Path to the CSV file")
    columns: list[ColumnSchema] = Field(
        default_factory=list, description="Column schema definitions"
    )
    filter_column: str | None = Field(
        default=None,
        description="Column to filter on using metadata.unit value",
    )
    delimiter: str = Field(default=",", description="CSV delimiter")
    encoding: str = Field(default="utf-8", description="File encoding")
    skip_rows: int = Field(default=0, description="Rows to skip before header")
    strict: bool = Field(default=False, description="Fail on schema mismatch if True")


class CsvRetriever(BaseRetriever):
    """Retriever that reads CSV files with schema validation and type conversion.

    This retriever reads a CSV file, validates its structure against a defined
    schema, converts columns to the specified types, and can filter rows using
    :class:`PipelineMetadata`. Results are cached via :func:`mi_core.utils.cache`
    to avoid re-reading the same file repeatedly.
    """

    def __init__(self, config: CsvRetrieverConfig) -> None:
        """Initialize the typed CSV retriever.

        Args:
            config: Configuration specifying file path, schema, and parsing options.
        """
        super().__init__(config)

        self._file_path = Path(config.file_path)
        self._columns = {col.name: col for col in config.columns}
        self._filter_column = config.filter_column
        self._delimiter = config.delimiter
        self._encoding = config.encoding
        self._skip_rows = config.skip_rows
        self._strict = config.strict

    def retrieve(self, *, metadata: PipelineMetadata | None = None) -> pd.DataFrame:
        """Retrieve and parse the CSV file with type conversion.

        Args:
            metadata: Optional pipeline metadata. Defaults to None.

        Returns:
            DataFrame-like object with typed columns. Uses pandas when available,
            otherwise Polars if installed, else returns a list of dictionaries.

        Raises:
            FileNotFoundError: If the CSV file does not exist.
            ValueError: In strict mode, if schema validation fails.
        """
        with _tracer.start_as_current_span("csv.retrieve") as span:
            span.set_attribute(ATTR_COMPONENT_LAYER, "library")
            span.set_attribute("csv.file_path", str(self._file_path))
            span.set_attribute("csv.columns_count", len(self._columns))
            span.set_attribute("csv.filter_column", self._filter_column or "none")
            span.set_attribute("csv.strict_mode", self._strict)

            if not self._file_path.exists():
                message = f"CSV file not found: {self._file_path}"
                span.set_attribute("csv.file_found", False)
                span.record_exception(FileNotFoundError(message))
                if self._strict:
                    raise FileNotFoundError(message)
                self.logger.warning(message)
                return pd.DataFrame()

            span.set_attribute("csv.file_found", True)
            file_size = self._file_path.stat().st_size
            span.set_attribute("csv.file_size_bytes", file_size)

            start_read = time.perf_counter()
            with _tracer.start_as_current_span("csv.read") as read_span:
                read_span.set_attribute(ATTR_COMPONENT_LAYER, "library")
                df = self._read_csv()
            end_read = time.perf_counter()
            self.logger.debug(
                "CsvRetriever: _read_csv() took %.4f seconds", end_read - start_read
            )

            row_count = len(df)
            span.set_attribute("csv.rows_read", row_count)

            start_validate = time.perf_counter()
            with _tracer.start_as_current_span("csv.validate") as validate_span:
                validate_span.set_attribute(ATTR_COMPONENT_LAYER, "library")
                validate_span.set_attribute(
                    "csv.columns_to_validate", len(self._columns)
                )
                validate_schema(
                    df,
                    self._columns,
                    strict=self._strict,
                    logger=self.logger,
                    context="CSV",
                )
            end_validate = time.perf_counter()
            self.logger.debug(
                "CsvRetriever: _validate_schema() took %.4f seconds",
                end_validate - start_validate,
            )

            start_convert = time.perf_counter()
            with _tracer.start_as_current_span("csv.convert") as convert_span:
                convert_span.set_attribute(ATTR_COMPONENT_LAYER, "library")
                convert_span.set_attribute("csv.columns_to_convert", len(self._columns))
                df = apply_type_conversions(
                    df,
                    self._columns,
                    strict=self._strict,
                    logger=self.logger,
                )
            end_convert = time.perf_counter()
            self.logger.debug(
                "CsvRetriever: _apply_type_conversions() took %.4f seconds",
                end_convert - start_convert,
            )

            start_filter = time.perf_counter()
            with _tracer.start_as_current_span("csv.filter") as filter_span:
                filter_span.set_attribute(ATTR_COMPONENT_LAYER, "library")
                filter_span.set_attribute("csv.rows_before_filter", len(df))
                df = self._apply_metadata_filter(df, metadata)
                filter_span.set_attribute("csv.rows_after_filter", len(df))
                filter_span.set_attribute("csv.rows_filtered", row_count - len(df))
            end_filter = time.perf_counter()
            self.logger.debug(
                "CsvRetriever: _apply_metadata_filter() took %.4f seconds",
                end_filter - start_filter,
            )

            span.set_attribute("csv.rows_final", len(df))
            self.logger.info(
                "Retrieved %d records from %s", len(df), self._file_path.name
            )
            return df

    def _apply_metadata_filter(
        self, df: pd.DataFrame, metadata: PipelineMetadata | None
    ) -> pd.DataFrame:
        """Filter DataFrame rows based on pipeline metadata.

        Applies ``metadata.unit`` against ``filter_column`` when configured;
        logs and returns the unfiltered frame when metadata is absent or the
        column is missing.
        """
        if not self._filter_column:
            return df

        if not metadata:
            self.logger.warning(
                "Filter column '%s' configured but no metadata provided, skipping filter",
                self._filter_column,
            )
            return df

        if self._filter_column not in df.columns:
            message = f"Filter column '{self._filter_column}' not found in CSV"
            if self._strict:
                raise ValueError(message)
            self.logger.warning(message)
            return df

        filter_value = metadata.unit
        original_count = len(df)

        col_dtype = df[self._filter_column].dtype
        if pd.api.types.is_numeric_dtype(col_dtype):
            try:
                filter_value = type(df[self._filter_column].iloc[0])(filter_value)
            except (ValueError, TypeError):
                pass

        df = df.loc[df[self._filter_column] == filter_value].copy()
        filtered_count = len(df)

        self.logger.info(
            "Filtered %s=%s: %d -> %d records",
            self._filter_column,
            filter_value,
            original_count,
            filtered_count,
        )

        return df

    def _read_csv(self) -> pd.DataFrame:
        """Read the CSV file into a pandas DataFrame using the shared cache."""

        @cache(log_misses=True)
        def _load_csv_file(
            path: Path, delimiter: str, encoding: str, skip_rows: int
        ) -> pd.DataFrame:
            return pd.read_csv(
                path,
                delimiter=delimiter,
                encoding=encoding,
                skiprows=skip_rows,
            )

        return _load_csv_file(
            self._file_path,
            self._delimiter,
            self._encoding,
            self._skip_rows,
        )
