"""
Tests for ContextManager

Validates all context management functionality including:
- Basic get/set operations
- Deep copy snapshots for chain_of_work
- Context merging with update()
"""

import pytest
from src.core.context import ContextManager


class TestContextManagerBasics:
    """Test basic ContextManager operations"""

    def test_init_empty(self):
        """Test initialization with empty context"""
        context = ContextManager()
        assert context.get_all() == {}
        assert context.size() == 0

    def test_init_with_data(self):
        """Test initialization with initial data"""
        initial = {"user_id": 123, "pdf_path": "/tmp/file.pdf"}
        context = ContextManager(initial)
        assert context.get_all() == initial
        assert context.size() == 2

    def test_set_and_get(self):
        """Test setting and getting values"""
        context = ContextManager()
        context.set("amount", 1200)
        assert context.get("amount") == 1200

    def test_get_with_default(self):
        """Test getting non-existent key with default value"""
        context = ContextManager()
        assert context.get("missing_key") is None
        assert context.get("missing_key", 0) == 0
        assert context.get("missing_key", "default") == "default"

    def test_has(self):
        """Test checking if key exists"""
        context = ContextManager()
        assert not context.has("invoice_data")
        context.set("invoice_data", {"amount": 1200})
        assert context.has("invoice_data")

    def test_delete(self):
        """Test deleting keys"""
        context = ContextManager()
        context.set("temp_data", "value")
        assert context.has("temp_data")

        # Delete existing key
        assert context.delete("temp_data") is True
        assert not context.has("temp_data")

        # Delete non-existent key
        assert context.delete("temp_data") is False

    def test_clear(self):
        """Test clearing all context"""
        context = ContextManager({"a": 1, "b": 2, "c": 3})
        assert context.size() == 3

        context.clear()
        assert context.get_all() == {}
        assert context.size() == 0

    def test_size(self):
        """Test getting context size"""
        context = ContextManager()
        assert context.size() == 0

        context.set("a", 1)
        assert context.size() == 1

        context.set("b", 2)
        context.set("c", 3)
        assert context.size() == 3


class TestContextManagerUpdate:
    """Test context merging with update()"""

    def test_update_empty_context(self):
        """Test updating empty context"""
        context = ContextManager()
        context.update({"a": 1, "b": 2})
        assert context.get_all() == {"a": 1, "b": 2}

    def test_update_merge(self):
        """Test that update merges with existing data"""
        context = ContextManager({"a": 1, "b": 2})
        context.update({"b": 20, "c": 3})

        result = context.get_all()
        assert result == {"a": 1, "b": 20, "c": 3}
        assert result["b"] == 20  # b was updated
        assert result["c"] == 3   # c was added

    def test_update_nested_objects(self):
        """Test updating with nested objects"""
        context = ContextManager()
        context.update({"invoice_data": {"amount": 1200, "vendor": "ACME"}})
        context.update({"is_valid": True})

        result = context.get_all()
        assert result["invoice_data"]["amount"] == 1200
        assert result["is_valid"] is True


class TestContextManagerSnapshots:
    """Test snapshot functionality for chain_of_work"""

    def test_snapshot_creates_copy(self):
        """Test that snapshot creates a copy"""
        context = ContextManager({"a": 1, "b": 2})
        snapshot = context.snapshot()

        assert snapshot == {"a": 1, "b": 2}
        assert snapshot is not context._context  # Different objects

    def test_snapshot_deep_copy_simple(self):
        """Test that snapshot is a deep copy (simple values)"""
        context = ContextManager({"amount": 1200})
        snapshot = context.snapshot()

        # Modify context
        context.set("amount", 9999)

        # Snapshot should be unchanged
        assert snapshot["amount"] == 1200
        assert context.get("amount") == 9999

    def test_snapshot_deep_copy_nested(self):
        """Test that snapshot is a deep copy (nested objects)"""
        context = ContextManager()
        context.set("invoice_data", {"amount": 1200, "vendor": "ACME"})

        # Take snapshot
        snapshot_before = context.snapshot()

        # Modify nested object
        context._context["invoice_data"]["amount"] = 9999
        context._context["invoice_data"]["vendor"] = "NewCorp"

        # Snapshot should be unchanged (this is the KEY test for deep copy)
        assert snapshot_before["invoice_data"]["amount"] == 1200
        assert snapshot_before["invoice_data"]["vendor"] == "ACME"

        # Context should have new values
        assert context.get("invoice_data")["amount"] == 9999
        assert context.get("invoice_data")["vendor"] == "NewCorp"

    def test_snapshot_independence(self):
        """Test that multiple snapshots are independent"""
        context = ContextManager()

        # Snapshot 1
        context.set("data", {"value": 1})
        snapshot1 = context.snapshot()

        # Snapshot 2
        context.update({"data": {"value": 2}})
        snapshot2 = context.snapshot()

        # Snapshot 3
        context.update({"data": {"value": 3}})
        snapshot3 = context.snapshot()

        # All snapshots should be independent
        assert snapshot1["data"]["value"] == 1
        assert snapshot2["data"]["value"] == 2
        assert snapshot3["data"]["value"] == 3

    def test_get_all_vs_snapshot(self):
        """Test that get_all() is shallow copy while snapshot() is deep copy"""
        context = ContextManager()
        context.set("invoice", {"amount": 1200})

        # get_all() is shallow
        shallow = context.get_all()
        # snapshot() is deep
        deep = context.snapshot()

        # Modify nested object
        context._context["invoice"]["amount"] = 9999

        # Shallow copy is affected (shares reference to nested object)
        assert shallow["invoice"]["amount"] == 9999  # Changed!

        # Deep copy is NOT affected (has its own copy)
        assert deep["invoice"]["amount"] == 1200  # Unchanged!


class TestContextManagerChainOfWorkUsage:
    """Test realistic usage pattern for chain_of_work"""

    def test_chain_of_work_pattern(self):
        """Test typical chain_of_work snapshot pattern"""
        # Initialize workflow
        context = ContextManager()

        # === NODE 1: Extract ===
        input_node1 = context.snapshot()  # {} (empty)
        assert input_node1 == {}

        # Node executes, returns data
        context.update({"invoice_data": {"amount": 1200, "vendor": "ACME"}})

        output_node1 = context.snapshot()
        assert output_node1 == {"invoice_data": {"amount": 1200, "vendor": "ACME"}}

        # === NODE 2: Validate ===
        input_node2 = context.snapshot()
        assert input_node2 == {"invoice_data": {"amount": 1200, "vendor": "ACME"}}

        # Node executes
        context.update({"is_valid": True, "needs_approval": False})

        output_node2 = context.snapshot()
        assert output_node2 == {
            "invoice_data": {"amount": 1200, "vendor": "ACME"},
            "is_valid": True,
            "needs_approval": False
        }

        # === VERIFY SNAPSHOTS ARE INDEPENDENT ===
        # input_node1 should still be empty
        assert input_node1 == {}

        # output_node1 should still have only invoice_data
        assert output_node1 == {"invoice_data": {"amount": 1200, "vendor": "ACME"}}
        assert "is_valid" not in output_node1

        # input_node2 should match output_node1
        assert input_node2 == output_node1

    def test_chain_of_work_nested_modification(self):
        """Test that chain_of_work snapshots survive nested modifications"""
        context = ContextManager()

        # Node 1: Create invoice
        context.set("invoice", {"amount": 1200, "items": []})
        snapshot1 = context.snapshot()

        # Node 2: Add item to invoice
        context.get("invoice")["items"].append({"name": "Widget", "price": 100})
        snapshot2 = context.snapshot()

        # Node 3: Add another item
        context.get("invoice")["items"].append({"name": "Gadget", "price": 200})
        snapshot3 = context.snapshot()

        # Verify snapshots are independent
        assert len(snapshot1["invoice"]["items"]) == 0
        assert len(snapshot2["invoice"]["items"]) == 1
        assert len(snapshot3["invoice"]["items"]) == 2

        assert snapshot2["invoice"]["items"][0]["name"] == "Widget"
        assert snapshot3["invoice"]["items"][1]["name"] == "Gadget"


class TestContextManagerEdgeCases:
    """Test edge cases and error handling"""

    def test_init_copies_initial_context(self):
        """Test that initial context is copied, not referenced"""
        initial = {"data": {"value": 1}}
        context = ContextManager(initial)

        # Modify original
        initial["data"]["value"] = 999

        # Context should have copied value
        assert context.get("data")["value"] == 1

    def test_set_none_value(self):
        """Test setting None as a value"""
        context = ContextManager()
        context.set("nullable", None)
        assert context.has("nullable")
        assert context.get("nullable") is None

    def test_update_empty_dict(self):
        """Test updating with empty dict"""
        context = ContextManager({"a": 1})
        context.update({})
        assert context.get_all() == {"a": 1}

    def test_repr_and_str(self):
        """Test string representations"""
        context = ContextManager({"a": 1, "b": 2})

        repr_str = repr(context)
        assert "ContextManager" in repr_str
        assert "keys=" in repr_str
        assert "size=2" in repr_str

        str_str = str(context)
        assert "ContextManager" in str_str
        assert "{'a': 1, 'b': 2}" in str_str or "{'b': 2, 'a': 1}" in str_str
