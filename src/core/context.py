"""
Context Manager

Manages shared state between workflow nodes.
Provides methods to read, write, and snapshot context for traceability.

Design inspired by LangGraph's state management pattern.
See: /documentacion/INVESTIGACION-CONTEXT-MANAGEMENT.md
"""

import copy
from typing import Any, Dict, Optional
from .context_summary import ContextSummary, AnalysisEntry
from .context_utils.config_keys import CONFIG_KEYS


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
        self._summary: ContextSummary = ContextSummary()

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

    # ==========================================
    # Context Summary Methods (New)
    # ==========================================

    def get_summary(self) -> ContextSummary:
        """
        Get the context summary (for LLM consumption).

        Returns:
            ContextSummary with schema and metadata

        Example:
            >>> context = ContextManager({"amount": 1200})
            >>> summary = context.get_summary()
            >>> summary.schema
            {"amount": {"type": "number", "description": "..."}}
        """
        return self._summary

    def add_analysis(self, node_id: str, analyzed_keys: list, schema: dict) -> None:
        """
        Add a new analysis entry to the context summary.

        Called after InputAnalyzer processes a node.

        Args:
            node_id: ID of the node where analysis happened
            analyzed_keys: Keys that were analyzed
            schema: Schema generated for those keys

        Example:
            >>> context.add_analysis(
            ...     node_id="extract_text",
            ...     analyzed_keys=["document_text"],
            ...     schema={"document_text": {"type": "string", ...}}
            ... )
        """
        entry = AnalysisEntry(
            node_id=node_id,
            analyzed_keys=analyzed_keys,
            schema_generated=schema
        )
        self._summary.add_analysis(entry)

    def get_clean_context(self) -> Dict[str, Any]:
        """
        Get context without metadata (for E2B execution).

        Filters out all keys starting with '_' (metadata).

        Returns:
            Context with only real data (no metadata)

        Example:
            >>> context = ContextManager({"amount": 1200, "_meta": "..."})
            >>> context.get_clean_context()
            {"amount": 1200}  # _meta excluded
        """
        return {k: v for k, v in self._context.items() if not k.startswith("_")}

    def get_new_keys(self) -> set:
        """
        Get keys in current context that haven't been analyzed yet.

        Returns:
            Set of keys that are new (not in analysis history)

        Example:
            >>> context = ContextManager({"a": 1, "b": 2})
            >>> context.add_analysis("node1", ["a"], {...})
            >>> context.get_new_keys()
            {"b"}  # Only b is new
        """
        current_keys = set(self._context.keys())
        return self._summary.get_new_keys(current_keys)

    # ==========================================
    # Context Filtering Methods (New)
    # ==========================================

    def get_execution_context(self) -> Dict[str, Any]:
        """
        Get complete context for E2B execution (config + functional + metadata).

        This is the full context that gets injected into the E2B sandbox,
        including configuration, functional data, and internal metadata.

        Returns:
            Complete context dictionary

        Example:
            >>> context = ContextManager({
            ...     "pdf_data": "JVBERi...",
            ...     "db_host": "localhost",
            ...     "db_password": "secret",
            ...     "_analyzed_keys": ["pdf_data"]
            ... })
            >>> context.get_execution_context()
            {
                "pdf_data": "JVBERi...",
                "db_host": "localhost",
                "db_password": "secret",
                "_analyzed_keys": ["pdf_data"]
            }
        """
        return self._context.copy()

    def get_functional_context(self) -> Dict[str, Any]:
        """
        Get functional context for LLMs (without config or metadata).

        Filters out:
        - Configuration keys (db_host, db_password, email credentials, etc.)
        - Internal metadata (keys starting with '_')

        This is what InputAnalyzer, DataAnalyzer, and Validators receive.

        Returns:
            Context with only functional data

        Example:
            >>> context = ContextManager({
            ...     "pdf_data": "JVBERi...",
            ...     "email_body": "Please process...",
            ...     "db_host": "localhost",
            ...     "db_password": "secret",
            ...     "_analyzed_keys": ["pdf_data"]
            ... })
            >>> context.get_functional_context()
            {
                "pdf_data": "JVBERi...",
                "email_body": "Please process..."
            }
        """
        return {
            k: v for k, v in self._context.items()
            if not k.startswith('_') and k not in CONFIG_KEYS
        }

    def get_config_context(self) -> Dict[str, Any]:
        """
        Get configuration context for CodeGenerator.

        Includes only configuration keys:
        - Database credentials (db_host, db_password, database_schemas)
        - Email credentials (email_user, email_password)
        - API credentials (GCP_SERVICE_ACCOUNT_JSON, AWS keys, etc.)
        - Workflow configuration (client_slug, sender_whitelist, etc.)

        Returns:
            Context with only configuration

        Example:
            >>> context = ContextManager({
            ...     "pdf_data": "JVBERi...",
            ...     "db_host": "localhost",
            ...     "db_password": "secret",
            ...     "GCP_SERVICE_ACCOUNT_JSON": "{...}"
            ... })
            >>> context.get_config_context()
            {
                "db_host": "localhost",
                "db_password": "secret",
                "GCP_SERVICE_ACCOUNT_JSON": "{...}"
            }
        """
        return {
            k: v for k, v in self._context.items()
            if k in CONFIG_KEYS
        }
