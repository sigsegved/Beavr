"""Blackboard pattern for shared agent state."""

from __future__ import annotations

import logging
from datetime import datetime
from threading import Lock
from typing import Any

logger = logging.getLogger(__name__)


class Blackboard:
    """
    Shared state container for multi-agent coordination.

    The blackboard pattern allows agents to read/write shared state
    without direct coupling. All writes are timestamped and logged.
    """

    def __init__(self) -> None:
        """Initialize empty blackboard."""
        self._state: dict[str, Any] = {}
        self._history: list[dict[str, Any]] = []
        self._lock = Lock()

    def set(self, key: str, value: Any, source: str = "unknown") -> None:
        """
        Set a value on the blackboard.

        Args:
            key: State key
            value: Value to store
            source: Who is writing (for audit)
        """
        with self._lock:
            self._state[key] = value
            entry = {
                "timestamp": datetime.now().isoformat(),
                "action": "set",
                "key": key,
                "source": source,
            }
            self._history.append(entry)
            logger.debug(f"Blackboard: {source} set '{key}'")

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a value from the blackboard.

        Args:
            key: State key
            default: Default value if key not found

        Returns:
            Value or default
        """
        with self._lock:
            return self._state.get(key, default)

    def get_all(self) -> dict[str, Any]:
        """
        Get all current state.

        Returns:
            Copy of current state dictionary
        """
        with self._lock:
            return dict(self._state)

    def get_history(self) -> list[dict[str, Any]]:
        """
        Get history of all writes.

        Returns:
            List of write events
        """
        with self._lock:
            return list(self._history)

    def clear(self) -> None:
        """Clear all state (start of new cycle)."""
        with self._lock:
            self._state.clear()
            self._history.append(
                {
                    "timestamp": datetime.now().isoformat(),
                    "action": "clear",
                    "key": "*",
                    "source": "system",
                }
            )
            logger.debug("Blackboard: cleared")

    def has_key(self, key: str) -> bool:
        """Check if key exists."""
        with self._lock:
            return key in self._state

    def __repr__(self) -> str:
        with self._lock:
            keys = list(self._state.keys())
        return f"<Blackboard keys={keys}>"
