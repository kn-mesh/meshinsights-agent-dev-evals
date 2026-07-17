"""Retriever-stage payload that stores raw datasets and adapters.

Quick Start:
    from mi.core.objects import RetrieverDataObject

    rdo = RetrieverDataObject()
    rdo["csv"]["default"] = [{"id": 1}]
    rdo.api["devices"] = [{"device_id": "abc"}]  # created lazily
    devices = rdo["api"]["devices"]
"""

from dataclasses import dataclass, field
from typing import Any

from mi.core.objects import BaseDataObject


@dataclass
class RetrieverDataObject(BaseDataObject):
    """Flexible container returned by retrievers before hydration.

    Attributes:
        _internal_custom_data (dict[str, dict[str, Any]]): Lazily initialized
            mapping of adapter names to their scoped datasets.
        csv (dict[str, Any]): Well-defined structure for CSV-based adapters.
        <custom adapter> (dict[str, Any]): Created on-demand via attribute access
            (e.g., ``source.api["devices"]``).

    Example:
        >>> rdo = RetrieverDataObject()
        >>> rdo["csv"]["customers"] = [{"id": "1"}]
        >>> rdo["csv"]["customers"][0]["id"]
        '1'
    """

    # ========== Catch-All Adapter ==========
    _internal_custom_data: dict[str, dict[str, Any]] = field(default_factory=dict)

    # ========== Well-Defined Adapters ==========
    csv: dict[str, Any] = field(default_factory=dict)

    def __getattr__(self, name: str) -> dict[str, Any]:
        """Return a custom adapter bucket, creating it if needed.

        Args:
            name (str): Adapter identifier such as ``"api"`` or ``"snowflake"``.

        Returns:
            dict[str, Any]: Mutable mapping reserved for the adapter.

        Notes:
            Attribute access is the preferred way to read/write adapter data in
            hydrators (``source.csv["default"]`` or ``source.api["devices"]``).

        Example:
            >>> bucket = RetrieverDataObject().unknown_adapter
            >>> bucket == {}
            True
        """

        if name not in self._internal_custom_data:
            self._internal_custom_data[name] = {}
        return self._internal_custom_data[name]

    def __getitem__(self, key: str) -> dict[str, Any]:
        """Access adapter datasets using dictionary syntax.

        Args:
            key (str): Adapter name; ``"csv"`` resolves to the dedicated field.

        Returns:
            dict[str, Any]: Adapter bucket for storing retrieval results.

        Notes:
            Dictionary access is equivalent to attribute access and can be
            useful when adapter names are dynamic.

        Example:
            >>> rdo = RetrieverDataObject()
            >>> rdo["csv"]["customers"] = []
            >>> rdo["csv"]["customers"]
            []
        """

        match key:
            case "csv":
                return self.csv
            case _:
                if key not in self._internal_custom_data:
                    self._internal_custom_data[key] = {}
                return self._internal_custom_data[key]

    def __setitem__(self, key: str, value: dict[str, Any]) -> None:
        """Set the adapter bucket directly.

        Args:
            key (str): Adapter namespace.
            value (dict[str, Any]): Structured data collected by a retriever.

        Example:
            >>> rdo = RetrieverDataObject()
            >>> rdo["csv"] = {"customers": []}
            >>> rdo.csv["customers"]
            []
        """

        match key:
            case "csv":
                self.csv = value
            case _:
                self._internal_custom_data[key] = value
