"""Base abstractions for pipeline actions.

Provides BaseAction and BaseActionConfig for implementing custom
actions that execute side effects based on ActionDataObject decisions.

See docs/components/actions.md for examples and best practices.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar, TYPE_CHECKING
import logging

from pydantic import BaseModel, Field

from mi.core.objects import ActionDataObject

if TYPE_CHECKING:
    from mi.core.pipeline import PipelineMetadata

ADO = TypeVar("ADO", bound=ActionDataObject)


class BaseActionConfig(BaseModel):
    """Configuration parameters shared by action implementations.

    This lightweight model captures author-defined properties such as the action
    name and the logical scope (e.g., team, tenant, or product line). Use it to
    drive dependency injection or parameterized behavior inside custom action
    classes.

    Attributes:
        name (str): Human-friendly action identifier used in logs. Defaults to
            ``"none"``.
        scope (str): Names the logical boundary or namespace the action operates
            within. Defaults to ``"none"``.

    Example:
        >>> config = BaseActionConfig(name="notify_ops", scope="operations")
        >>> config.name
        'notify_ops'
    """

    name: str = Field(default="none", description="Name of the action")
    scope: str = Field(default="none", description="Scope of the action")


class BaseAction(ABC, Generic[ADO]):
    """Abstract base class for actions that finalize pipeline results.

    Actions mutate or inspect an :class:`ActionDataObject` and typically trigger
    real-world effects such as sending emails or exporting datasets. Subclasses
    are invoked sequentially during the act stage of a pipeline and should be
    written to be idempotent when possible.

    Attributes:
        name (str): Action identifier automatically derived from the class name
            unless explicitly provided.
        config (dict[str, Any]): Arbitrary configuration dictionary made
            available to subclasses for runtime tuning.
        logger (logging.Logger): Stage-aware logger for structured observability.

    Example:
        >>> from mi.core.objects import ActionDataObject
        >>> class PrintAction(BaseAction[ActionDataObject]):
        ...     def act(self, data_object: ActionDataObject) -> None:
        ...         self.logger.info("Decision keys: %s", data_object.list_decisions())
        >>> action = PrintAction(name="printer", config={"channel": "stdout"})
        >>> action.name
        'printer'
    """

    def __init__(
        self, name: str | None = None, config: dict[str, Any] | None = None
    ) -> None:
        """Initialize a base action with optional overrides.

        Args:
            name (str | None): Explicit action name. Defaults to the class name
                if ``None``.
            config (dict[str, Any] | None): Free-form configuration dictionary
                parsed from pipeline YAML or builder code. Defaults to an empty
                dictionary.

        Example:
            >>> from mi.core.objects import ActionDataObject
            >>> class CustomAction(BaseAction[ActionDataObject]):
            ...     def __init__(self) -> None:
            ...         super().__init__(name="custom", config={"scope": "beta"})
            ...     def act(self, data_object: ActionDataObject) -> None:
            ...         self.logger.info("Acting on %s", data_object.object_id)
            >>> CustomAction().name
            'custom'
        """

        self.name = name or self.__class__.__name__
        self.config = config or {}
        self.logger = logging.getLogger(f"action.{self.name}")

    @abstractmethod
    def act(
        self, data_object: ADO, *, metadata: PipelineMetadata | None = None
    ) -> None:
        """Execute the action logic for the provided data object.

        Args:
            data_object (ADO): The action data structure containing accumulated
                decisions and artifacts from previous stages.
            metadata: Optional pipeline metadata (e.g., unit_id). Defaults to None
                if not provided.

        Notes:
            Raise exceptions to signal failures; the enclosing :class:`Pipeline`
            respects the pipeline's ``error_action`` policy when handling them.

        Example:
            >>> from mi.core.objects import ActionDataObject
            >>> class NotifyAction(BaseAction[ActionDataObject]):
            ...     def act(self, data_object: ActionDataObject, *, metadata=None) -> None:
            ...         message = data_object.get_decision("message")
            ...         self.logger.info("Sending: %s", message)
        """

        pass
