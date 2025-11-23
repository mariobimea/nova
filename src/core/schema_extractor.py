"""
Schema Extractor - Extract compact data schemas for semantic caching.

This module analyzes workflow context to extract a compact, structured
representation of input data for semantic code matching.

Key features:
- Detects data types (str, int, float, bool, list, dict)
- Identifies large base64 data
- Extracts CSV column structure
- Parses JSON structure
- Separates credentials from data structure
"""

import json
import logging
import re
import base64
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

# Fields that contain credentials (should go to config, not schema)
CREDENTIAL_FIELDS = {
    'client_slug',
    'db_host', 'db_port', 'db_user', 'db_password', 'db_name',
    'email_user', 'email_password', 'imap_host', 'smtp_host',
    'imap_port', 'smtp_port',
    'gcp_service_account_json',
    'api_key', 'api_secret', 'access_token', 'refresh_token',
    'private_key', 'public_key', 'secret_key'
}


def extract_compact_schema(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract a compact type schema from context.

    Analyzes values to determine types, detects large data (base64, CSV, JSON),
    and returns a compact representation suitable for semantic matching.

    Args:
        context: Workflow execution context

    Returns:
        Compact schema dict with type information

    Example:
        >>> context = {
        ...     "invoice_number": "INV-001",
        ...     "amount": 1500.50,
        ...     "items": [{"name": "Item 1"}],
        ...     "pdf_data": "JVBERi0xLjQKJeLjz9MK..." (very long base64)
        ... }
        >>> schema = extract_compact_schema(context)
        >>> schema
        {
            "invoice_number": "str",
            "amount": "float",
            "items": "list[dict]",
            "pdf_data": "base64_large"
        }
    """
    schema = {}

    for key, value in context.items():
        # Skip internal fields
        if key.startswith('_'):
            continue

        # Extract type
        schema[key] = _extract_type(value)

    return schema


def _extract_type(value: Any) -> str:
    """
    Extract type string from value.

    Detects:
    - Basic types: str, int, float, bool, None
    - Collections: list, dict
    - Special formats: base64_large, csv, json_dict, json_list
    """
    if value is None:
        return "null"

    # Basic types
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"

    # String analysis
    if isinstance(value, str):
        # Empty string
        if not value:
            return "str_empty"

        # Large base64 (>1000 chars, likely file data)
        if len(value) > 1000 and _is_base64(value):
            return "base64_large"

        # CSV format
        if _looks_like_csv(value):
            columns = _extract_csv_columns(value)
            if columns:
                return f"csv[{len(columns)}]"
            return "csv"

        # JSON format
        if _looks_like_json(value):
            parsed = _try_parse_json(value)
            if parsed is not None:
                if isinstance(parsed, dict):
                    return "json_dict"
                elif isinstance(parsed, list):
                    return "json_list"

        # Regular string
        return "str"

    # List
    if isinstance(value, list):
        if not value:
            return "list_empty"

        # Analyze first element to infer list type
        first_type = _extract_type(value[0])
        return f"list[{first_type}]"

    # Dict
    if isinstance(value, dict):
        if not value:
            return "dict_empty"

        # Count keys
        return f"dict[{len(value)}]"

    # Unknown type
    return str(type(value).__name__)


def _is_base64(value: str) -> bool:
    """
    Check if string is base64 encoded.

    Heuristic: Contains only base64 chars (A-Za-z0-9+/=)
    and length is multiple of 4.
    """
    if not value:
        return False

    # Base64 pattern
    base64_pattern = r'^[A-Za-z0-9+/]*={0,2}$'
    if not re.match(base64_pattern, value):
        return False

    # Length should be multiple of 4
    if len(value) % 4 != 0:
        return False

    # Try to decode (quick check)
    try:
        base64.b64decode(value[:100], validate=True)
        return True
    except Exception:
        return False


def _looks_like_csv(value: str) -> bool:
    """
    Check if string looks like CSV data.

    Heuristics:
    - Contains newlines
    - Lines have consistent comma/tab separators
    - At least 2 rows
    """
    if '\n' not in value:
        return False

    lines = value.strip().split('\n')
    if len(lines) < 2:
        return False

    # Check for consistent separators
    first_line_commas = lines[0].count(',')
    first_line_tabs = lines[0].count('\t')

    # Need at least one separator
    if first_line_commas == 0 and first_line_tabs == 0:
        return False

    # Check consistency in next few lines
    for line in lines[1:min(5, len(lines))]:
        if abs(line.count(',') - first_line_commas) > 1:
            return False

    return True


def _extract_csv_columns(value: str) -> List[str]:
    """
    Extract column names from CSV data.

    Assumes first row is header.

    Returns:
        List of column names, or [] if cannot extract
    """
    try:
        lines = value.strip().split('\n')
        if not lines:
            return []

        # Get first line (header)
        header = lines[0]

        # Detect separator
        if ',' in header:
            columns = [col.strip().strip('"') for col in header.split(',')]
        elif '\t' in header:
            columns = [col.strip().strip('"') for col in header.split('\t')]
        else:
            return []

        return [col for col in columns if col]

    except Exception as e:
        logger.debug(f"Could not extract CSV columns: {e}")
        return []


def _looks_like_json(value: str) -> bool:
    """
    Check if string looks like JSON.

    Heuristic: Starts with { or [
    """
    stripped = value.strip()
    return stripped.startswith('{') or stripped.startswith('[')


def _try_parse_json(value: str) -> Any:
    """
    Try to parse string as JSON.

    Returns:
        Parsed JSON object, or None if not valid JSON
    """
    try:
        return json.loads(value)
    except Exception:
        return None


def build_cache_context(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build cache context from workflow context.

    Separates:
    - input_schema: Data structure (for semantic matching)
    - config: Credential flags (for filtering)
    - insights: Context insights (from InputAnalyzer)

    Args:
        context: Full workflow context

    Returns:
        Cache context dict with structure:
        {
            "input_schema": {...},
            "config": {...},
            "insights": [...]
        }

    Example:
        >>> context = {
        ...     "client_slug": "acme",
        ...     "db_password": "secret123",
        ...     "invoice_pdf": "JVBERi0...",
        ...     "database_schemas": {...}
        ... }
        >>> cache_ctx = build_cache_context(context)
        >>> cache_ctx
        {
            "input_schema": {
                "invoice_pdf": "base64_large",
                "database_schemas": {...}  # Simplified
            },
            "config": {
                "has_client_slug": True,
                "has_db_password": True
            },
            "insights": []
        }
    """
    input_schema = {}
    config = {}
    insights = []

    for key, value in context.items():
        # Skip internal fields
        if key.startswith('_'):
            continue

        # Credentials → config (as boolean flags)
        if key.lower() in CREDENTIAL_FIELDS:
            config[f"has_{key}"] = value is not None and value != ""
            continue

        # Database schemas → special handling
        if key == "database_schemas":
            if isinstance(value, dict):
                input_schema[key] = _simplify_db_schema(value)
            else:
                input_schema[key] = _extract_type(value)
            continue

        # Regular data → schema
        input_schema[key] = _extract_type(value)

    return {
        "input_schema": input_schema,
        "config": config,
        "insights": insights  # Will be populated by GraphEngine
    }


def _simplify_db_schema(schemas: Dict[str, Any]) -> Dict[str, Any]:
    """
    Simplify database_schemas for caching.

    Keeps structure (tables, columns, types) but removes defaults
    and other non-essential metadata.

    Args:
        schemas: Full database schemas dict

    Returns:
        Simplified schemas dict
    """
    simplified = {}

    for table_name, table_schema in schemas.items():
        if not isinstance(table_schema, dict):
            simplified[table_name] = str(type(table_schema).__name__)
            continue

        # Keep essential fields only
        simplified_table = {}

        if 'columns' in table_schema:
            simplified_table['columns'] = table_schema['columns']

        if 'types' in table_schema:
            simplified_table['types'] = table_schema['types']

        if 'nullable' in table_schema:
            simplified_table['nullable'] = table_schema['nullable']

        if 'primary_key' in table_schema:
            simplified_table['primary_key'] = table_schema['primary_key']

        # Omit: defaults, foreign_keys, indexes (not needed for code generation)

        simplified[table_name] = simplified_table

    return simplified
