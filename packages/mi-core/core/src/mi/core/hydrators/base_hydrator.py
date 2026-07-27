"""Hydrator abstractions that convert data between pipeline stages.

Hydrators handle the transformation of data objects produced by one stage into
the format required by the next stage while recording useful metadata on the
pipeline receipt.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar, TYPE_CHECKING
import logging

from pydantic import BaseModel, Field

from mi.core.pipeline_receipt import PipelineReceipt
from mi.core.objects import BaseDataObject

if TYPE_CHECKING:
    from mi.core.pipeline import PipelineMetadata

IDO = TypeVar("IDO", bound=BaseDataObject, default=BaseDataObject)
ODO = TypeVar("ODO", bound=BaseDataObject | None, default=BaseDataObject | None)


class BaseHydratorConfig(BaseModel):
    """Configuration shared by hydrator implementations.

    Attributes:
        name (str): Identifier that is appended to the logger namespace.
        scope (str): Optional namespace for differentiating hydrators by data
            domain.

    Example:
        >>> BaseHydratorConfig(name="process", scope="customers").model_dump()  # doctest: +ELLIPSIS
        {'name': 'process', 'scope': 'customers'}
    """

    name: str = Field(default="none", description="Name of the hydrator")
    scope: str = Field(default="none", description="Scope of the hydrator")


class BaseHydrator(ABC, Generic[IDO, ODO]):
    """Base class for hydrators orchestrating stage transitions.

    Hydrators read from a source data object, optionally persist artifacts on
    the :class:`PipelineReceipt`, then output a transformed data object that the
    next stage can consume. Use hydrators to enforce consistent normalization
    between teams and to stamp receipts with observability metadata.

    Quick Start:
        from mi.core.hydrators import BaseHydrator
        from mi.core.objects import RetrieverDataObject, ProcessDataObject
        from mi.core.pipeline_receipt import PipelineReceipt

        class RetrieverToProcess(BaseHydrator[RetrieverDataObject, ProcessDataObject]):
            def hydrate(self, source: RetrieverDataObject, receipt: PipelineReceipt, *, metadata=None) -> ProcessDataObject:
                process = ProcessDataObject()
                process.normalized_data[\"default\"] = source.csv.get(\"default\", [])
                return process

        Attributes:
            name (str): Logger namespace derived from the hydrator class name.
            logger (logging.Logger): Shared pipeline logger child for consistent log
                formatting.

        Example:
            >>> from mi.core.objects import RetrieverDataObject, ProcessDataObject
            >>> from mi.core.pipeline_receipt import PipelineReceipt
            >>> class RetrieverToProcess(BaseHydrator[RetrieverDataObject, ProcessDataObject]):
            ...     def hydrate(self, source: RetrieverDataObject, receipt: PipelineReceipt) -> ProcessDataObject:
            ...         receipt.set_metadata("source", list(source.csv.keys()))
            ...         return ProcessDataObject()
            >>> hydrator = RetrieverToProcess()
            >>> isinstance(hydrator.logger.name, str)
            True
    """

    def __init__(self, name: str | None = None) -> None:
        """Initialize a hydrator and bind a stage-aware logger.

        Args:
            name (str | None): Explicit hydrator name. Defaults to the class
                name.

        Example:
            >>> from mi.core.objects import BaseDataObject
            >>> from mi.core.pipeline_receipt import PipelineReceipt
            >>> class IdentityHydrator(BaseHydrator[BaseDataObject, BaseDataObject]):
            ...     def hydrate(self, source: BaseDataObject, receipt: PipelineReceipt) -> BaseDataObject:
            ...         return source
            >>> IdentityHydrator().name  # doctest: +ELLIPSIS
            'IdentityHydrator'
        """

        self.name = name or self.__class__.__name__
        self.logger = logging.getLogger(f"hydrator.{self.name}")

    @abstractmethod
    def hydrate(
        self,
        source: IDO,
        receipt: PipelineReceipt,
        *,
        metadata: PipelineMetadata | None = None,
    ) -> ODO:
        """Transform the source object into the next stage's payload.

        Args:
            source (IDO): Data object emitted by the previous pipeline stage.
            receipt (PipelineReceipt): Pipeline execution record used for
                storing metadata or tracing.
            metadata: Optional pipeline metadata (e.g., unit_id). Defaults to None
                if not provided.

        Returns:
            ODO: The hydrated data object prepared for the next stage. May be
                ``None`` for terminal hydrators.

        Notes:
            Hydrators may raise exceptions; the pipeline will honor its
            ``error_action`` policy when deciding whether to stop or continue.

        Example:
            >>> from mi.core.objects import ProcessDataObject
            >>> from mi.core.pipeline_receipt import PipelineReceipt
            >>> class FinalizeHydrator(BaseHydrator[ProcessDataObject, None]):
            ...     def hydrate(self, source: ProcessDataObject, receipt: PipelineReceipt, *, metadata=None) -> None:
            ...         receipt.set_metadata("final_count", len(source.artifacts))
            ...         return None
        """

        pass
