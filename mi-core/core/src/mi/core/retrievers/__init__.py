"""Retriever primitives that source external data for pipelines.

Retrievers run first in the pipeline lifecycle, collecting raw datasets
from files, APIs, or databases. The ``config.name``/``config.scope`` pair
determines how results are keyed on ``RetrieverDataObject``.

See docs/components/retrievers.md for examples and configuration reference.
"""
# ruff: noqa: F401

from .base_retriever import BaseRetriever, BaseRetrieverConfig

try:
    import importlib.util

    if importlib.util.find_spec("pandas") is not None:
        from .csv_retriever import ColumnSchema, CsvRetriever, CsvRetrieverConfig
        from .json_retriever import FieldSchema, JsonRetriever, JsonRetrieverConfig

        __all__ = [
            # shared retriever parent
            "BaseRetriever",
            "BaseRetrieverConfig",
            # csv retriever
            "ColumnSchema",
            "CsvRetriever",
            "CsvRetrieverConfig",
            # json retriever
            "FieldSchema",
            "JsonRetriever",
            "JsonRetrieverConfig",
        ]
    else:
        __all__ = [
            # shared retriever parent
            "BaseRetriever",
            "BaseRetrieverConfig",
        ]
except ImportError:
    # do nothing here, Python will always import this BEFORE relative imports so debug info cannot be put here
    pass

    __all__ = [
        # shared retriever parent
        "BaseRetriever",
        "BaseRetrieverConfig",
    ]
