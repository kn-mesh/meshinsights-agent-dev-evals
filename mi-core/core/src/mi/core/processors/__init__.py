"""Processor components that transform and analyze pipeline data.

Processors read from normalized_data on ProcessDataObject, compute
metrics and transformations, and store results as artifacts.

See docs/components/processors.md for examples and best practices.
"""
# ruff: noqa: F401

from .base_processor import BaseProcessor, BaseProcessorConfig

__all__ = [
    "BaseProcessor",
    "BaseProcessorConfig",
]
