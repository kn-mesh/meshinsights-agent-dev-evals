"""Process-stage payload that stores normalized datasets and artifacts.

Quick Start:
    from mi.core.objects import ProcessDataObject

    process = ProcessDataObject()
    process.normalized_data["customers"] = [{"id": 1, "active": True}]
    process.set_artifact("metrics.active_count", 1)
    active_count = process.get_artifact("metrics.active_count")
    customers = process.get_dataset("customers")
"""

from dataclasses import dataclass, field
from typing import Any

from mi.core.objects import BaseDataObject


@dataclass
class ProcessDataObject(BaseDataObject):
    """Data container exchanged between processors and hydrators.

    Processors enrich ``normalized_data`` with deterministic datasets and persist
    intermediate results inside ``artifacts`` for future components or debugging.

    Attributes:
        normalized_data (dict[str, Any]): Mapping of dataset name to arbitrary
            structured payloads used by processors.
        artifacts (dict[str, Any]): Free-form storage for processor outputs that
            do not belong in normalized datasets.

    Example:
        >>> process = ProcessDataObject()
        >>> process.normalized_data["raw_customers"] = [{"id": 1}]
        >>> _ = process.set_artifact("record_count", 1)
        >>> process.get_dataset("raw_customers")[0]["id"]
        1
    """

    # ========== Core Data ==========
    normalized_data: dict[str, Any] = field(default_factory=dict)

    # ========== Processing Results / Data ==========
    artifacts: dict[str, Any] = field(default_factory=dict)

    def get_dataset(self, key: str) -> Any:
        """Return a normalized dataset by key.

        Args:
            key (str): Name of the dataset that was populated by a retriever or
                processor.

        Returns:
            Any: The dataset referenced by ``key``.

        Raises:
            KeyError: If no dataset with the supplied ``key`` exists.

        Notes:
            This accessor intentionally raises when the dataset is missing to
            surface upstream configuration errors early.

        Example:
            >>> pdo = ProcessDataObject()
            >>> pdo.normalized_data["customers"] = []
            >>> pdo.get_dataset("customers")
            []
        """

        return self.normalized_data[key]

    def set_artifact(self, key: str, value: Any) -> "ProcessDataObject":
        """Store an artifact and return ``self`` for chaining.

        Args:
            key (str): Identifier under which the artifact will be stored.
            value (Any): Serializable payload that captures processor output.

        Returns:
            ProcessDataObject: The same instance, enabling fluent mutation.

        Notes:
            Artifacts are typically used for derived metrics, intermediate
            feature sets, or flags that downstream processors/actions need.

        Example:
            >>> ProcessDataObject().set_artifact("record_count", 42).artifacts["record_count"]
            42
        """

        self.artifacts[key] = value
        return self

    def get_artifact(self, key: str) -> Any:
        """Retrieve an artifact if it exists.

        Args:
            key (str): Artifact identifier.

        Returns:
            Any: Stored artifact value or ``None`` when not set.

        Example:
            >>> ProcessDataObject().get_artifact("missing") is None
            True
        """

        return self.artifacts.get(key, None)

    def list_artifacts(self, prefix: str | None = None) -> list[str]:
        """List stored artifact keys optionally filtered by prefix.

        Args:
            prefix (str | None): Restrict results to keys beginning with this
                string. Returns all keys by default.

        Returns:
            list[str]: Artifact identifiers sorted by insertion order.

        Example:
            >>> process = ProcessDataObject()
            >>> process.set_artifact("metrics.total", 1)
            ProcessDataObject(...)
            >>> process.list_artifacts("metrics.")
            ['metrics.total']
        """

        keys = list(self.artifacts.keys())
        return [k for k in keys if prefix is None or k.startswith(prefix)]
