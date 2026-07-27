"""Helpers for converting pandas DataFrames into LLM-safe strings."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    import pandas as pd

DataFrameStringFormat = Literal["dataframe", "csv", "json", "markdown"]


def convert_dataframe_to_string(
    dataframe: "pd.DataFrame",
    string_format: DataFrameStringFormat | str = "csv",
) -> str:
    """Convert a DataFrame to a full, untruncated string representation.

    Supported formats:
    - ``dataframe``: full ``DataFrame.to_string(index=False)`` with display limits disabled
    - ``csv``: ``DataFrame.to_csv(index=False)``
    - ``json``: ``DataFrame.to_json(orient='records', date_format='iso')``
    - ``markdown``: ``DataFrame.to_markdown(index=False)``
    """
    pd = _require_pandas()
    if not isinstance(dataframe, pd.DataFrame):
        raise TypeError("dataframe must be a pandas DataFrame")

    fmt = (string_format or "").strip().lower()

    if fmt == "csv":
        return dataframe.to_csv(index=False)

    if fmt == "json":
        return dataframe.to_json(orient="records", date_format="iso")

    if fmt == "markdown":
        return dataframe.to_markdown(index=False)

    if fmt == "" or fmt == "dataframe":
        with pd.option_context(
            "display.max_rows",
            None,
            "display.max_columns",
            None,
            "display.width",
            None,
            "display.max_colwidth",
            None,
            "display.expand_frame_repr",
            True,
        ):
            return dataframe.to_string(index=False)

    raise ValueError(
        f"Unsupported string_format '{string_format}'. Supported: "
        "'dataframe', 'csv', 'json', 'markdown'."
    )


def is_pandas_dataframe(value: object) -> bool:
    """Return True when ``value`` is a pandas DataFrame."""
    try:
        import pandas as pd
    except ImportError:
        return False
    return isinstance(value, pd.DataFrame)


def _require_pandas() -> Any:
    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError(
            "pandas is required for DataFrame conversion support. "
            "Install with 'pip install pandas' or include mi-core AI dependencies."
        ) from exc
    return pd
