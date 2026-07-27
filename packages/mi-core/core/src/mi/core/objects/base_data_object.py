"""Base data object providing correlation and object ID tracking.

All pipeline data objects inherit from BaseDataObject, which
automatically generates correlation_id and object_id for
tracing data through the pipeline.

See docs/components/data-objects.md for the data object hierarchy.
"""

from dataclasses import dataclass, field
from typing import Final
from uuid import uuid4


@dataclass
class BaseDataObject:
    """Common metadata container propagated through the pipeline.

    Each specialized data object inherits the automatically generated identifiers
    defined here, enabling downstream systems to correlate logs, receipts, and
    stored artifacts across stages.

    Attributes:
        correlation_id (str): Stable identifier shared between related objects.
        object_id (str): Unique identifier for the specific data object instance.

    Example:
        >>> base = BaseDataObject()
        >>> base.correlation_id != base.object_id
        True
    """

    # ========== Object Metadata ==========
    correlation_id: Final[str] = field(default_factory=lambda: str(uuid4()))
    object_id: Final[str] = field(default_factory=lambda: str(uuid4()))
