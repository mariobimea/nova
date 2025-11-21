"""
Cache Utilities
Functions for generating cache keys based on prompt + full context hash
"""

import hashlib
import json
from typing import Dict, Any


def generate_cache_key(prompt: str, context: Dict[str, Any]) -> str:
    """
    Generate cache key based on prompt + complete context hash.

    The cache key is a SHA256 hash that includes:
    1. Normalized prompt (lowercase, stripped)
    2. Hash of the ENTIRE context (all keys and values)

    This ensures that:
    - Same prompt + same context → Same cache key → Cache HIT
    - Same prompt + different context → Different cache key → Cache MISS

    Args:
        prompt: Task description (e.g., "Extract invoice total from PDF")
        context: Complete execution context with all data

    Returns:
        64-character SHA256 hash

    Example:
        >>> prompt = "Extract text from PDF"
        >>> context = {"pdf_data": b"...", "client_id": 123}
        >>> key = generate_cache_key(prompt, context)
        >>> print(key)
        "a3f5b9c2d4e6f8a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6"
    """
    # 1. Normalize prompt (lowercase, strip whitespace)
    normalized_prompt = prompt.lower().strip()

    # 2. Generate hash of complete context
    context_hash = hash_context(context)

    # 3. Combine prompt + context_hash
    cache_input = f"{normalized_prompt}::{context_hash}"

    # 4. Generate final SHA256 hash
    return hashlib.sha256(cache_input.encode('utf-8')).hexdigest()


def hash_context(context: Dict[str, Any]) -> str:
    """
    Generate SHA256 hash of complete context.

    Hashes ALL keys and values, including:
    - Strings (full content)
    - Bytes (PDF data, images, etc.)
    - Numbers, booleans
    - Nested dicts and lists (recursive)

    Args:
        context: Complete context dictionary

    Returns:
        64-character SHA256 hash

    Example:
        >>> context = {"pdf_data": b"...", "client_id": 123}
        >>> hash_context(context)
        "c5d6e7f8g9h0i1j2k3l4m5n6o7p8q9r0s1t2u3v4w5x6y7z8a9b0c1d2e3f4a5b6"
    """
    hasher = hashlib.sha256()

    # Process each key in sorted order (for consistency)
    for key in sorted(context.keys()):
        value = context[key]

        # Add key to hash
        hasher.update(key.encode('utf-8'))

        # Add value hash
        value_hash = hash_value(value)
        hasher.update(value_hash.encode('utf-8'))

    return hasher.hexdigest()


def hash_value(value: Any) -> str:
    """
    Generate SHA256 hash of a single value.

    Handles all Python types:
    - bytes: Hash complete binary data
    - str: Hash complete string
    - int, float, bool: Convert to string and hash
    - dict: Recursive hash (same as hash_context)
    - list: Hash each item
    - None: Hash as "null"

    Args:
        value: Any Python value

    Returns:
        64-character SHA256 hash
    """

    if isinstance(value, bytes):
        # Binary data (PDF, images, etc.)
        # Hash COMPLETE content
        return hashlib.sha256(value).hexdigest()

    elif isinstance(value, str):
        # String (CSV, JSON, email text, etc.)
        # Hash COMPLETE content
        return hashlib.sha256(value.encode('utf-8')).hexdigest()

    elif isinstance(value, bool):
        # Boolean (must check before int, since bool is subclass of int)
        return hashlib.sha256(str(value).lower().encode('utf-8')).hexdigest()

    elif isinstance(value, (int, float)):
        # Numbers
        return hashlib.sha256(str(value).encode('utf-8')).hexdigest()

    elif isinstance(value, dict):
        # Nested dictionary (recursive)
        return hash_context(value)

    elif isinstance(value, list):
        # List (hash each item in order)
        hasher = hashlib.sha256()
        for item in value:
            item_hash = hash_value(item)
            hasher.update(item_hash.encode('utf-8'))
        return hasher.hexdigest()

    elif value is None:
        # None/null
        return hashlib.sha256(b'null').hexdigest()

    else:
        # Fallback: convert to string
        # (handles custom objects, Decimal, datetime, etc.)
        return hashlib.sha256(str(value).encode('utf-8')).hexdigest()


def generate_task_hash(prompt: str) -> str:
    """
    Generate hash of prompt only (for analytics/grouping).

    This is used separately from cache_key to group similar tasks,
    even if they have different contexts.

    Args:
        prompt: Task description

    Returns:
        64-character SHA256 hash

    Example:
        >>> generate_task_hash("Extract invoice total")
        "d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1f2a3b4c5"
    """
    normalized_prompt = prompt.lower().strip()
    return hashlib.sha256(normalized_prompt.encode('utf-8')).hexdigest()


def extract_context_schema(context: Dict[str, Any]) -> Dict[str, str]:
    """
    Extract schema (structure) from context.

    Returns a dict with keys and their Python types (as strings).
    This is used for optional schema-based analytics, NOT for cache key.

    Args:
        context: Complete context

    Returns:
        Schema dict with type names

    Example:
        >>> context = {"pdf_data": b"...", "client_id": 123, "active": True}
        >>> extract_context_schema(context)
        {"pdf_data": "bytes", "client_id": "int", "active": "bool"}
    """
    schema = {}

    for key, value in context.items():
        # Get Python type name
        type_name = type(value).__name__
        schema[key] = type_name

    return schema


def generate_context_schema_hash(context: Dict[str, Any]) -> str:
    """
    Generate hash of context schema (structure only).

    This is used for optional analytics, NOT for cache key generation.

    Args:
        context: Complete context

    Returns:
        64-character SHA256 hash of schema

    Example:
        >>> context = {"pdf_data": b"...", "client_id": 123}
        >>> generate_context_schema_hash(context)
        "e6f7g8h9i0j1k2l3m4n5o6p7q8r9s0t1u2v3w4x5y6z7a8b9c0d1e2f3a4b5c6d7"
    """
    schema = extract_context_schema(context)
    schema_str = json.dumps(schema, sort_keys=True)
    return hashlib.sha256(schema_str.encode('utf-8')).hexdigest()
