"""
Context Manager

Manages shared state between workflow nodes.
Provides methods to read, write, and snapshot context for traceability.

Design inspired by LangGraph's state management pattern.
See: /documentacion/INVESTIGACION-CONTEXT-MANAGEMENT.md
"""

import copy
from typing import Any, Dict, Optional


class ContextManager:
    """
    Centralized context manager for workflow execution.

    The context acts as shared memory between nodes, allowing them to:
    - Read data produced by previous nodes
    - Write data for subsequent nodes
    - Maintain state throughout workflow execution

    Example:
        >>> context = ContextManager()
        >>> context.set("invoice_data", {"amount": 1200})
        >>> context.get("invoice_data")
        {"amount": 1200}
        >>> context.update({"is_valid": True})
        >>> context.get_all()
        {"invoice_data": {"amount": 1200}, "is_valid": True}
    """

    def __init__(self, initial_context: Optional[Dict[str, Any]] = None):
        """
        Initialize the context manager.

        Args:
            initial_context: Optional initial context data.
                            Useful for passing trigger data (e.g., {"pdf_path": "/tmp/file.pdf"})

        Example:
            >>> # Empty context (most common)
            >>> context = ContextManager()

            >>> # Context with initial data
            >>> context = ContextManager({"user_id": 123, "pdf_path": "/tmp/invoice.pdf"})
        """
        self._context: Dict[str, Any] = initial_context.copy() if initial_context else {}

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a single value from the context.

        Args:
            key: The key to retrieve
            default: Default value if key doesn't exist

        Returns:
            The value associated with the key, or default if not found

        Example:
            >>> context.set("amount", 1200)
            >>> context.get("amount")
            1200
            >>> context.get("missing_key", 0)
            0
        """
        return self._context.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """
        Set a single value in the context.

        Args:
            key: The key to set
            value: The value to store

        Example:
            >>> context.set("invoice_data", {"amount": 1200, "vendor": "ACME"})
            >>> context.set("is_valid", True)
        """
        self._context[key] = value

    def update(self, data: Dict[str, Any]) -> None:
        """
        Update multiple values at once (merge with existing context).

        This is the primary method used after executing a node in Hetzner.
        The returned context from Hetzner gets merged into the existing context.

        Args:
            data: Dictionary with keys to update

        Example:
            >>> context = ContextManager({"a": 1, "b": 2})
            >>> context.update({"b": 20, "c": 3})
            >>> context.get_all()
            {"a": 1, "b": 20, "c": 3}  # b was updated, c was added
        """
        self._context.update(data)

    def get_all(self) -> Dict[str, Any]:
        """
        Get the complete context as a dictionary.

        Returns a shallow copy to prevent direct modification of internal state.
        Use this method when injecting context into Hetzner sandbox.

        Returns:
            Copy of the complete context

        Example:
            >>> context = ContextManager({"a": 1, "b": 2})
            >>> full_ctx = context.get_all()
            >>> full_ctx
            {"a": 1, "b": 2}

        Note:
            This returns a SHALLOW copy. For immutable snapshots (e.g., chain_of_work),
            use snapshot() instead to get a deep copy.
        """
        return self._context.copy()

    def snapshot(self) -> Dict[str, Any]:
        """
        Create an immutable deep copy of the current context.

        Use this method when saving context to chain_of_work for audit trail.
        Deep copy ensures that future modifications don't affect saved snapshots.

        Returns:
            Deep copy of the complete context

        Example:
            >>> context = ContextManager()
            >>> context.set("invoice", {"amount": 1200})
            >>> snapshot_before = context.snapshot()
            >>> context.update({"invoice": {"amount": 9999}})
            >>> snapshot_before
            {"invoice": {"amount": 1200}}  # Unchanged!

        See Also:
            /documentacion/INVESTIGACION-CONTEXT-MANAGEMENT.md
            Section "5.3 Inyección en Hetzner Sandbox" for usage pattern
        """
        return copy.deepcopy(self._context)

    def clear(self) -> None:
        """
        Clear all context data.

        Primarily used for testing. Not typically used in production.

        Example:
            >>> context = ContextManager({"a": 1, "b": 2})
            >>> context.clear()
            >>> context.get_all()
            {}
        """
        self._context = {}

    def has(self, key: str) -> bool:
        """
        Check if a key exists in the context.

        Args:
            key: The key to check

        Returns:
            True if key exists, False otherwise

        Example:
            >>> context.set("invoice_data", {...})
            >>> context.has("invoice_data")
            True
            >>> context.has("missing_key")
            False
        """
        return key in self._context

    def delete(self, key: str) -> bool:
        """
        Delete a key from the context.

        Args:
            key: The key to delete

        Returns:
            True if key was deleted, False if key didn't exist

        Example:
            >>> context.set("temp_data", "value")
            >>> context.delete("temp_data")
            True
            >>> context.delete("temp_data")
            False
        """
        if key in self._context:
            del self._context[key]
            return True
        return False

    def size(self) -> int:
        """
        Get the number of keys in the context.

        Returns:
            Number of keys

        Example:
            >>> context = ContextManager({"a": 1, "b": 2, "c": 3})
            >>> context.size()
            3
        """
        return len(self._context)

    def __repr__(self) -> str:
        """String representation for debugging."""
        return f"<ContextManager(keys={list(self._context.keys())}, size={self.size()})>"

    def __str__(self) -> str:
        """Human-readable string representation."""
        return f"ContextManager({self._context})"
