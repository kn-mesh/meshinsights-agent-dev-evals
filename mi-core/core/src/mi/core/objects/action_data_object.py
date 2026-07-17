"""Action-stage payload that stores downstream decisions and side effects.

Quick Start:
    from mi.core.objects import ActionDataObject

    action = ActionDataObject()
    action.set_decision("threshold.heating_stage_1", 1200)

    # Discover keys before calling get_decision to avoid KeyError
    if "threshold.heating_stage_1" in action.list_decisions():
        value = action.get_decision("threshold.heating_stage_1")
"""

from dataclasses import dataclass, field
from typing import Any

from mi.core.objects import BaseDataObject


@dataclass
class ActionDataObject(BaseDataObject):
    """Data transfer object consumed by pipeline actions and hydrators.

    Attributes:
        decision (dict[str, Any]): Mapping of decision keys to resolved values
            used by hydrators and actions to drive notifications, exports, etc.

    Example:
        >>> action_object = ActionDataObject()
        >>> _ = action_object.set_decision("email.subject", "Hello")
        >>> action_object.get_decision("email.subject")
        'Hello'
    """

    # ========== Decision Data ==========
    decision: dict[str, Any] = field(default_factory=dict)

    def get_decision(self, key: str) -> Any:
        """Return a stored decision value.

        Args:
            key (str): Decision identifier such as ``"email.subject"``.

        Returns:
            Any: The stored decision payload.

        Raises:
            KeyError: If the key does not exist in ``decision``.

        Notes:
            Use :meth:`list_decisions` to discover available keys before calling
            this accessor to avoid unintentionally raising a ``KeyError``.

        Example:
            >>> obj = ActionDataObject()
            >>> _ = obj.set_decision("route", "email")
            >>> obj.get_decision("route")
            'email'
        """

        return self.decision[key]

    def set_decision(self, key: str, value: Any) -> "ActionDataObject":
        """Persist a decision result and return ``self`` for chaining.

        Args:
            key (str): Decision identifier.
            value (Any): Value associated with the decision (e.g., template name,
                serialized payload).

        Returns:
            ActionDataObject: Same instance with updated decision.

        Notes:
            Any existing value for ``key`` is overwritten. Use this from
            hydrators or processors to pass outcomes to subsequent actions.

        Example:
            >>> ActionDataObject().set_decision("channel", "sms").decision["channel"]
            'sms'
        """

        self.decision[key] = value
        return self

    def list_decisions(self, prefix: str | None = None) -> list[str]:
        """Enumerate decision keys, optionally filtered by prefix.

        Args:
            prefix (str | None): Include only keys that start with this prefix
                when provided.

        Returns:
            list[str]: Decision identifiers sorted by insertion order.

        Example:
            >>> obj = ActionDataObject()
            >>> _ = obj.set_decision("email.subject", "Hello")
            >>> obj.list_decisions("email.")
            ['email.subject']
        """

        keys = list(self.decision.keys())
        return [k for k in keys if prefix is None or k.startswith(prefix)]
