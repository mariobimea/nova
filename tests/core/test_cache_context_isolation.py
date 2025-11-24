"""
Test that cache_context doesn't pollute the context hash.

Verifies that adding cache_context as a parameter (not in context)
doesn't change the exact cache key.
"""

import pytest
from src.core.cache_utils import generate_cache_key
from src.core.schema_extractor import build_cache_context


def test_cache_context_not_in_context():
    """Test that cache_context is NOT added to context."""
    context = {
        "pdf_data": "JVBERi0xLjQK" + "A" * 2000,
        "client": "ACME Corp"
    }

    # Build cache context (should not modify context)
    cache_context = build_cache_context(context)

    # Verify context was NOT modified
    assert "_cache_context" not in context
    assert len(context) == 2  # Still only 2 keys


def test_cache_key_stability():
    """Test that cache key is stable when cache_context is separate."""
    prompt = "Extract text from PDF"
    context = {
        "pdf_data": "JVBERi0xLjQK" + "A" * 2000,
        "client": "ACME Corp"
    }

    # Generate cache key BEFORE creating cache_context
    key1 = generate_cache_key(prompt, context)

    # Build cache_context (should not modify context)
    cache_context = build_cache_context(context)

    # Generate cache key AFTER creating cache_context
    key2 = generate_cache_key(prompt, context)

    # Cache keys should be IDENTICAL
    assert key1 == key2, "Cache key changed after building cache_context!"


def test_cache_context_separation():
    """Test that cache_context is properly separated from context."""
    context = {
        "pdf_data": "JVBERi0xLjQK",
        "db_password": "secret123",
        "amount": 1500.50
    }

    cache_context = build_cache_context(context)

    # Cache context should have credentials as flags
    assert "has_db_password" in cache_context["config"]
    assert cache_context["config"]["has_db_password"] is True

    # Original context should still have raw credentials
    assert "db_password" in context
    assert context["db_password"] == "secret123"

    # Cache context should NOT have raw credentials
    assert "db_password" not in cache_context["input_schema"]
    assert "db_password" not in cache_context["config"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
