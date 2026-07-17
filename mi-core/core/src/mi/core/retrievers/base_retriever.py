"""Base abstractions for pipeline retrievers.

Provides BaseRetriever and BaseRetrieverConfig for implementing
custom data source integrations. Set config.name and config.scope
before calling super().__init__().

See docs/components/retrievers.md for examples and best practices.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Final, TYPE_CHECKING
import logging

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from mi.core.pipeline import PipelineMetadata


class BaseRetrieverConfig(BaseModel):
    """Configuration shared by retriever implementations.

    Attributes:
        name (str): Identifier used for logging and as the top-level dataset key.
        scope (str): Names the logical partition serviced by the retriever
            (e.g., ``"default"``, ``"customers"``, ``"orders"``).

    Example:
        >>> BaseRetrieverConfig(name="customers", scope="na").model_dump()["scope"]
        'na'
    """

    name: str = Field(default="default", description="Name of the retriever")
    scope: str = Field(default="default", description="Scope of the retriever")


class BaseRetriever(ABC):
    """Abstract base class for retrieving raw pipeline inputs.

    Attributes:
        name (str): Derived from the config or the class name.
        scope (str): Logical namespace that downstream hydrators use to route
            datasets. The pipeline will store results under
            ``retrieved_data[name][scope]``.
        logger (logging.Logger): Stage-aware logger.

    Example:
        >>> class ConstantRetriever(BaseRetriever):
        ...     def __init__(self) -> None:
        ...         super().__init__(BaseRetrieverConfig(name="const", scope="default"))
        ...     def retrieve(self) -> list[dict[str, str]]:
        ...         return [{"id": "1"}]
        >>> ConstantRetriever().scope
        'default'
    """

    name: Final[str]
    scope: Final[str]
    logger: Final[logging.Logger]

    def __init__(self, config: BaseRetrieverConfig | None) -> None:
        """Bind config-derived metadata and initialize a logger.

        Args:
            config (BaseRetrieverConfig | None): Component configuration. When
                ``None``, defaults are inferred from the class metadata.

        Notes:
            Set ``config.name`` and ``config.scope`` *before* calling
            ``super().__init__`` in subclasses so the pipeline stores results
            under the intended keys.

        Example:
            >>> class InlineConfigRetriever(BaseRetriever):
            ...     def __init__(self) -> None:
            ...         super().__init__(BaseRetrieverConfig(name="inline", scope="beta"))
            ...     def retrieve(self) -> dict[str, str]:
            ...         return {"status": "ok"}
            >>> InlineConfigRetriever().name
            'inline'
        """

        self.name = getattr(config, "name", self.__class__.__name__)
        self.scope = getattr(config, "scope", "default")
        self.logger = logging.getLogger(f"retriever.{self.name}")

    @abstractmethod
    def retrieve(self, *, metadata: PipelineMetadata | None = None) -> Any:
        """Collect external data and return it as a Python object.

        Args:
            metadata: Optional pipeline metadata (e.g., unit_id). Defaults to None
                if not provided.

        Returns:
            Any: Structured payload, typically a dictionary or list of records.
                The pipeline wraps this under ``{name: {scope: return_value}}``.

        Example:
            >>> class StaticRetriever(BaseRetriever):
            ...     def __init__(self) -> None:
            ...         super().__init__(BaseRetrieverConfig(name="static"))
            ...     def retrieve(self, *, metadata=None) -> list[int]:
            ...         return [1, 2, 3]
        """

        pass
