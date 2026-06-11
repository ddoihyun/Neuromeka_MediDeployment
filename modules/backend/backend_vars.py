"""Thread-safe storage for values shared between backend threads.

The previous version of this helper exposed a large dictionary-like surface
area (attribute access, context managers, deletion, etc.). In practice the
backend only relies on three core operations: **read**, **write**, and
**update**. This module now focuses on those primitives so callers can see a
straightforward, self-contained API at a glance.
"""

from __future__ import annotations

from copy import deepcopy
from threading import RLock
from typing import Any, Dict, Optional
from datetime import datetime


def _utc_timestamp() -> str:
    return datetime.utcnow().isoformat() + "Z"


class BackendVars:
    """Minimal thread-safe key/value store."""

    def __init__(self, initial: Optional[Dict[str, Any]] = None) -> None:
        self._lock = RLock()
        self._vars = dict(initial or {})

    def read(self, name: str, default: Any = None) -> Any:
        """Return ``name`` or ``default`` if provided.

        A defensive ``deepcopy`` is used so callers cannot mutate the stored
        value without an explicit ``write`` call.
        """

        with self._lock:
            if name in self._vars:
                return deepcopy(self._vars[name])
            if default is not None:
                return deepcopy(default)
            raise KeyError(name)

    def write(self, name: str, value: Any) -> Any:
        """Store ``value`` under ``name`` and return the stored copy."""

        with self._lock:
            self._vars[name] = self._normalize(name, value)
            return deepcopy(self._vars[name])

    def update(self, mapping: Dict[str, Any]) -> Dict[str, Any]:
        """Atomically merge a dictionary of updates and return the snapshot."""

        if not isinstance(mapping, dict):
            raise TypeError("mapping must be a dict")

        with self._lock:
            for key, value in mapping.items():
                self._vars[key] = self._normalize(key, value)
            return deepcopy(self._vars)

    # ``get``/``set`` aliases keep the public API self-explanatory without
    # introducing additional surface area.
    get = read
    set = write

    def _normalize(self, name: str, value: Any) -> Any:
        """Prepare values before storage.

        ``SYSTEM_STATUS`` writes automatically receive a fresh ``last_updated``
        timestamp when one is not provided, so external producers don't need to
        remember to supply it.
        """

        if name == "SYSTEM_STATUS" and isinstance(value, dict):
            normalized = deepcopy(value)
            normalized.setdefault("last_updated", _utc_timestamp())
            return normalized

        return deepcopy(value)


