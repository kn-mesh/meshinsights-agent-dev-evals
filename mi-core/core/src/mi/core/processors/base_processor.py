"""Base abstractions for pipeline processors.

Provides BaseProcessor and BaseProcessorConfig for implementing
custom data transformation and analysis logic.

See docs/components/processors.md for examples and best practices.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar, TYPE_CHECKING
import logging
import time
from pydantic import BaseModel, Field

from mi.core.objects import ProcessDataObject

if TYPE_CHECKING:
    from mi.core.pipeline import PipelineMetadata

PDO = TypeVar("PDO", bound=ProcessDataObject, default=ProcessDataObject)


class BaseProcessorConfig(BaseModel):
    """Base configuration model for processor implementations.

    Subclass this to create typed configurations for your processors.
    All fields are validated by Pydantic at instantiation time.

    Attributes:
        name: Optional human-friendly identifier used in logs.
        stop_on_error: Hint used by callers to decide whether to halt the
            pipeline when this processor raises.

    Example:
        class MyConfig(BaseProcessorConfig):
            threshold: float = 0.5
            enabled: bool = True

        config = MyConfig(name="detector", threshold=0.8)
    """

    name: str | None = Field(
        default=None, description="Optional name for the processor"
    )
    stop_on_error: bool = Field(
        default=True, description="Whether to stop pipeline on errors"
    )

    model_config = {"extra": "allow"}  # Allow subclasses to add fields


class BaseProcessor(ABC, Generic[PDO]):
    """Abstract base class that shapes processor behavior.

    Subclass this class to implement deterministic transformations on a
    :class:`ProcessDataObject`. Processors can validate prerequisites, mutate
    normalized datasets, and emit artifacts for downstream consumers. The
    default ``__call__`` wrapper records timing and logs errors consistently.

    Type Parameters:
        PDO: The ProcessDataObject subclass this processor operates on.
        ConfigT: The configuration model class (defaults to BaseProcessorConfig).

    Attributes:
        name: Instance identifier derived from config or class name.
        config: Typed configuration instance.
        logger: Pipeline logger child used for structured logs.

    Example:
        class MyConfig(BaseProcessorConfig):
            multiplier: int = 2

        class MyProcessor(BaseProcessor[ProcessDataObject, MyConfig]):
            def process(self, data_object: ProcessDataObject, *, metadata=None) -> None:
                value = data_object.normalized_data.get("value", 0)
                data_object.set_artifact("result", value * self.config.multiplier)

        processor = MyProcessor(MyConfig(multiplier=3))
    """

    def __init__(self, config: BaseProcessorConfig | None = None) -> None:
        """Initialize the processor with a typed configuration.

        Args:
            config: Configuration instance. If None, creates a default instance
                using the config_class attribute.

        Example:
            processor = MyProcessor(MyConfig(name="custom", threshold=0.9))
            processor = MyProcessor()  # Uses default config
        """
        if config is None:
            config = BaseProcessorConfig()

        self.config = config
        self.name = config.name or self.__class__.__name__
        self.logger = logging.getLogger(f"processor.{self.name}")

    @abstractmethod
    def process(
        self, data_object: PDO, *, metadata: PipelineMetadata | None = None
    ) -> None:
        """Execute the processor's main logic.

        Args:
            data_object: The shared process data object containing raw and
                normalized datasets.
            metadata: Optional pipeline metadata (e.g., unit_id).

        Example:
            def process(self, data_object: ProcessDataObject, *, metadata=None) -> None:
                total = len(data_object.normalized_data.get("customers", []))
                data_object.set_artifact("customer_count", total)
        """
        pass

    def validate_prerequisites(self, data_object: PDO) -> None:
        """Ensure the processor has the inputs it requires.

        Args:
            data_object: The object whose ``normalized_data`` entry should
                contain at least one dataset.

        Raises:
            ValueError: If ``normalized_data`` is empty and the processor has no
                data to work with.
        """
        if not data_object.normalized_data:
            raise ValueError(
                f"{self.name}: No normalized_data datasets available for processing"
            )

    def validate_output(self, data_object: PDO) -> None:
        """Perform post-processing validation.

        Override this hook to confirm that the processor produced the artifacts
        required by downstream components.

        Args:
            data_object: The mutated data object after ``process`` runs.
        """
        pass

    def __call__(
        self, data_object: PDO, *, metadata: PipelineMetadata | None = None
    ) -> None:
        """Execute the full processor lifecycle with logging and validation.

        Args:
            data_object: Object to mutate throughout the processor execution.
            metadata: Optional pipeline metadata.

        Raises:
            Exception: Propagates any unhandled exception raised inside the
                lifecycle to allow the pipeline to honor ``error_action``.
        """
        start_time = time.time()
        self.logger.info(f"Starting {self.name}")

        try:
            self.validate_prerequisites(data_object)
            self.process(data_object, metadata=metadata)
            self.validate_output(data_object)

            execution_time = time.time() - start_time
            self.logger.info(f"Completed {self.name} in {execution_time:.2f}s")

        except Exception as e:
            self.logger.error(f"Error in {self.name}: {str(e)}", exc_info=True)
            raise
