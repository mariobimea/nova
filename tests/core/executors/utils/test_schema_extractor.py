"""
Tests for Schema Extractor

Tests extraction of compact data schemas for semantic caching.
"""

import pytest
import base64
from src.core.schema_extractor import (
    extract_compact_schema,
    build_cache_context,
    _extract_type,
    _is_base64,
    _looks_like_csv,
    _extract_csv_columns,
    _simplify_db_schema
)


def test_extract_basic_types():
    """Test extraction of basic Python types."""
    context = {
        "name": "John Doe",
        "age": 30,
        "salary": 50000.50,
        "is_active": True,
        "middle_name": None
    }

    schema = extract_compact_schema(context)

    assert schema["name"] == "str"
    assert schema["age"] == "int"
    assert schema["salary"] == "float"
    assert schema["is_active"] == "bool"
    assert schema["middle_name"] == "null"


def test_detect_base64_large():
    """Test detection of large base64 data."""
    # Generate large base64 string
    large_data = b"x" * 2000
    large_base64 = base64.b64encode(large_data).decode('ascii')

    context = {
        "pdf_data": large_base64
    }

    schema = extract_compact_schema(context)
    assert schema["pdf_data"] == "base64_large"


def test_detect_csv():
    """Test detection and extraction of CSV data."""
    csv_data = """name,age,email
John Doe,30,john@example.com
Jane Smith,25,jane@example.com
Bob Johnson,35,bob@example.com"""

    context = {
        "user_data": csv_data
    }

    schema = extract_compact_schema(context)
    # Should detect CSV with 3 columns
    assert "csv" in schema["user_data"]
    assert "[3]" in schema["user_data"]


def test_extract_csv_columns():
    """Test CSV column extraction."""
    csv_data = "name,age,email\nJohn,30,john@example.com"
    columns = _extract_csv_columns(csv_data)

    assert columns == ["name", "age", "email"]


def test_detect_json():
    """Test detection of JSON data."""
    import json

    json_dict = json.dumps({"key1": "value1", "key2": "value2"})
    json_list = json.dumps([1, 2, 3, 4, 5])

    context = {
        "config": json_dict,
        "items": json_list
    }

    schema = extract_compact_schema(context)
    assert schema["config"] == "json_dict"
    assert schema["items"] == "json_list"


def test_list_and_dict_types():
    """Test extraction of list and dict types."""
    context = {
        "items": [{"name": "Item 1"}, {"name": "Item 2"}],
        "settings": {"theme": "dark", "language": "en"},
        "numbers": [1, 2, 3],
        "empty_list": [],
        "empty_dict": {}
    }

    schema = extract_compact_schema(context)
    # Each dict in list has 1 key ("name"), not 2 items
    assert schema["items"] == "list[dict[1]]"
    assert schema["settings"] == "dict[2]"
    assert schema["numbers"] == "list[int]"
    assert schema["empty_list"] == "list_empty"
    assert schema["empty_dict"] == "dict_empty"


def test_build_cache_context_separates_credentials():
    """Test that credentials are separated into config."""
    context = {
        "client_slug": "acme_corp",
        "db_password": "secret123",
        "db_host": "localhost",
        "invoice_pdf": "JVBERi0xLjQK" + "A" * 2000,  # Large base64
        "amount": 1500.50
    }

    cache_ctx = build_cache_context(context)

    # Credentials should be in config as boolean flags
    assert "has_client_slug" in cache_ctx["config"]
    assert cache_ctx["config"]["has_client_slug"] is True
    assert "has_db_password" in cache_ctx["config"]
    assert cache_ctx["config"]["has_db_password"] is True

    # Data should be in input_schema
    assert "invoice_pdf" in cache_ctx["input_schema"]
    assert cache_ctx["input_schema"]["invoice_pdf"] == "base64_large"
    assert "amount" in cache_ctx["input_schema"]
    assert cache_ctx["input_schema"]["amount"] == "float"

    # Credentials should NOT be in input_schema
    assert "client_slug" not in cache_ctx["input_schema"]
    assert "db_password" not in cache_ctx["input_schema"]


def test_simplify_database_schemas():
    """Test simplification of database_schemas."""
    full_schema = {
        "invoices": {
            "columns": ["id", "invoice_number", "amount", "created_at"],
            "types": ["INTEGER", "VARCHAR", "DECIMAL", "TIMESTAMP"],
            "nullable": [False, False, False, True],
            "primary_key": ["id"],
            "defaults": [None, None, None, "NOW()"],
            "indexes": ["idx_invoice_number"]
        },
        "clients": {
            "columns": ["id", "name", "email"],
            "types": ["INTEGER", "VARCHAR", "VARCHAR"],
            "nullable": [False, False, True],
            "primary_key": ["id"]
        }
    }

    simplified = _simplify_db_schema(full_schema)

    # Should keep essential fields
    assert "columns" in simplified["invoices"]
    assert "types" in simplified["invoices"]
    assert "nullable" in simplified["invoices"]
    assert "primary_key" in simplified["invoices"]

    # Should omit non-essential fields
    assert "defaults" not in simplified["invoices"]
    assert "indexes" not in simplified["invoices"]


def test_build_cache_context_with_database_schemas():
    """Test cache context with database_schemas field."""
    context = {
        "database_schemas": {
            "users": {
                "columns": ["id", "name"],
                "types": ["INTEGER", "VARCHAR"],
                "nullable": [False, False],
                "primary_key": ["id"],
                "defaults": [None, None]
            }
        },
        "query": "SELECT * FROM users"
    }

    cache_ctx = build_cache_context(context)

    # database_schemas should be simplified
    assert "database_schemas" in cache_ctx["input_schema"]
    db_schema = cache_ctx["input_schema"]["database_schemas"]
    assert "columns" in db_schema["users"]
    assert "defaults" not in db_schema["users"]


def test_skip_internal_fields():
    """Test that internal fields (starting with _) are skipped."""
    context = {
        "_internal": "should_skip",
        "_cache_context": {"foo": "bar"},
        "regular_field": "should_include"
    }

    schema = extract_compact_schema(context)

    assert "_internal" not in schema
    assert "_cache_context" not in schema
    assert "regular_field" in schema


def test_empty_context():
    """Test with empty context."""
    context = {}
    cache_ctx = build_cache_context(context)

    assert cache_ctx["input_schema"] == {}
    assert cache_ctx["config"] == {}
    assert cache_ctx["insights"] == []


def test_is_base64_validation():
    """Test base64 detection heuristics."""
    # Valid base64
    valid_base64 = base64.b64encode(b"Hello World").decode('ascii')
    assert _is_base64(valid_base64) is True

    # Invalid base64 (not multiple of 4)
    assert _is_base64("ABC") is False

    # Invalid base64 (contains invalid chars)
    assert _is_base64("Hello World!") is False

    # Empty string
    assert _is_base64("") is False


def test_looks_like_csv_validation():
    """Test CSV detection heuristics."""
    # Valid CSV (with actual newlines, not escaped)
    valid_csv = "name,age\nJohn,30\nJane,25"
    assert _looks_like_csv(valid_csv) is True

    # Invalid CSV (no newlines)
    assert _looks_like_csv("name,age,email") is False

    # Invalid CSV (inconsistent columns)
    very_inconsistent = "name,age\nJohn\nJane,25,extra,more"
    assert _looks_like_csv(very_inconsistent) is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
