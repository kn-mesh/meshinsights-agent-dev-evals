"""Type-safe data objects that flow through pipeline stages.

Provides RetrieverDataObject, ProcessDataObject, and ActionDataObject
as typed containers for raw data, normalized data with artifacts,
and structured decisions respectively.

See docs/components/data-objects.md for usage patterns.
"""
# ruff: noqa: F401

from .base_data_object import BaseDataObject
from .process_data_object import ProcessDataObject
from .retriever_data_object import RetrieverDataObject
from .action_data_object import ActionDataObject

__all__ = [
    # shared data object parent
    "BaseDataObject",
    # pipeline data objects
    "ProcessDataObject",
    "ActionDataObject",
    "RetrieverDataObject",
]
