"""Execution receipts capturing pipeline run outcomes.

Each pipeline run returns a PipelineReceipt with per-stage timing,
error details, and custom metadata recorded during execution.

See docs/architecture.md for the receipt data model.
"""

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4


@dataclass
class StageReceipt:
    """Stores timing, success status, and metadata for a single stage.

    Attributes:
        stage_name (str): Identifies the stage (``"retrieve"``, ``"process"``,
            or ``"act"``).
        success (bool): Flag denoting whether the stage completed without
            raising.
        execution_time_seconds (float): Duration of the stage.
        error (str | None): Optional human-readable error description.
        correlation_id (str): Unique identifier per stage execution. Use this
            when correlating logs to downstream telemetry.
        metadata (dict[str, Any]): Custom attributes appended by components for
            debugging or analytics (e.g., counts, filter criteria).

    Example:
        >>> receipt = StageReceipt(stage_name="process", success=True, execution_time_seconds=0.5)
        >>> receipt.set_metadata("processor_count", 3).get_metadata("processor_count")
        3
    """

    # ========== Stage Metadata ==========
    stage_name: str
    success: bool
    execution_time_seconds: float

    # ========== Stage Results ==========
    error: str | None = None
    correlation_id: str = field(default_factory=lambda: str(uuid4()))
    metadata: dict[str, Any] = field(default_factory=dict)

    def set_metadata(self, key: str, value: Any) -> "StageReceipt":
        """Store a metadata entry for the stage.

        Args:
            key (str): Metadata key.
            value (Any): Serializable value such as a count or identifier.

        Returns:
            StageReceipt: ``self`` to enable fluent chaining.

        Example:
            >>> StageReceipt("retrieve", True, 0.1).set_metadata("retrievers", 2)  # doctest: +ELLIPSIS
            StageReceipt(stage_name='retrieve', success=True, execution_time_seconds=0.1, error=None, correlation_id=..., metadata={'retrievers': 2})
        """

        self.metadata[key] = value
        return self

    def get_metadata(self, key: str) -> Any:
        """Retrieve stored metadata, returning ``None`` when missing.

        Args:
            key (str): Metadata identifier.

        Returns:
            Any: Stored value or ``None``.

        Example:
            >>> StageReceipt("retrieve", True, 0.1).get_metadata("missing") is None
            True
        """

        return self.metadata.get(key, None)


@dataclass
class PipelineReceipt:
    """Aggregate record capturing the full pipeline execution.

    Attributes:
        pipeline_id (str): Unique identifier per pipeline run.
        correlation_id (str): Secondary identifier used for distributed tracing.
        retrieve_receipt (StageReceipt | None): Receipt for the retrieve stage.
        process_receipt (StageReceipt | None): Receipt for the process stage.
        act_receipt (StageReceipt | None): Receipt for the act stage.
        config (dict[str, Any]): Snapshot of key pipeline configuration values.
            This makes receipts self-describing when stored or inspected later.
        success (bool): Whether the whole pipeline succeeded.
        total_execution_time_seconds (float): End-to-end runtime.

    Example:
        >>> receipt = PipelineReceipt(pipeline_id="demo")
        >>> receipt.set_config("name", "demo").get_config("name")
        'demo'
    """

    # ========== Pipeline Metadata ==========
    pipeline_id: str
    correlation_id: str = field(default_factory=lambda: str(uuid4()))

    # ========== Stage Receipts ==========
    retrieve_receipt: StageReceipt | None = None
    process_receipt: StageReceipt | None = None
    act_receipt: StageReceipt | None = None

    # ========== Pipeline Configuration ==========
    config: dict[str, Any] = field(default_factory=dict)

    # ========== Overall Pipeline Results ==========
    success: bool = True
    total_execution_time_seconds: float = 0.0

    def set_config(self, key: str, value: Any) -> "PipelineReceipt":
        """Persist a configuration attribute for future inspection.

        Args:
            key (str): Configuration key.
            value (Any): Serialized configuration value.

        Returns:
            PipelineReceipt: ``self`` for chaining.

        Example:
            >>> PipelineReceipt("demo").set_config("version", "1.0").config["version"]
            '1.0'
        """

        self.config[key] = value
        return self

    def get_config(self, key: str) -> Any:
        """Read a configuration attribute from the receipt.

        Args:
            key (str): Configuration key to read.

        Returns:
            Any: Stored value or ``None`` if absent.

        Example:
            >>> PipelineReceipt("demo").get_config("missing") is None
            True
        """

        return self.config.get(key, None)

    def get_stage_receipt(self, stage_name: str) -> StageReceipt | None:
        """Return a stage receipt by name.

        Args:
            stage_name (str): Name of the stage to inspect (case-insensitive).

        Returns:
            StageReceipt | None: Receipt for the requested stage or ``None`` if
                it has not run.

        Example:
            >>> receipt = PipelineReceipt("demo")
            >>> receipt.retrieve_receipt = StageReceipt("retrieve", True, 0.1)
            >>> isinstance(receipt.get_stage_receipt("retrieve"), StageReceipt)
            True
        """

        stage_map = {
            "retrieve": self.retrieve_receipt,
            "process": self.process_receipt,
            "act": self.act_receipt,
        }
        return stage_map.get(stage_name.lower())

    def is_stage_successful(self, stage_name: str) -> bool:
        """Check whether a stage succeeded, returning ``False`` if unknown.

        Args:
            stage_name (str): Name of the stage to evaluate.

        Returns:
            bool: ``True`` when the stage completed successfully, otherwise
                ``False``.

        Example:
            >>> receipt = PipelineReceipt("demo")
            >>> receipt.process_receipt = StageReceipt("process", False, 0.2)
            >>> receipt.is_stage_successful("process")
            False
        """

        receipt = self.get_stage_receipt(stage_name)
        return receipt.success if receipt else False
