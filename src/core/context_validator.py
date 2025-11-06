"""
Context Validator & Sanitizer

Ensures that workflow context only contains JSON-serializable data.
Prevents crashes from non-serializable Python objects (email.Message, file handles, etc.)

Usage:
    from context_validator import sanitize_context, validate_context

    # Option 1: Validate (raises error if invalid)
    validate_context(context)

    # Option 2: Sanitize (cleans automatically)
    clean_context = sanitize_context(context)
"""

import json
import logging
from typing import Any, Dict, List, Set, Tuple
from datetime import datetime, date
from decimal import Decimal

logger = logging.getLogger(__name__)


class ContextValidationError(Exception):
    """Raised when context contains non-serializable data"""
    pass


# Types that are JSON-serializable
SAFE_TYPES = (str, int, float, bool, type(None))


def is_json_serializable(value: Any) -> Tuple[bool, str]:
    """
    Check if a value is JSON-serializable.

    Args:
        value: Value to check

    Returns:
        Tuple of (is_safe, reason_if_not_safe)

    Examples:
        >>> is_json_serializable("hello")
        (True, "")

        >>> is_json_serializable({"a": 1})
        (True, "")

        >>> import email
        >>> msg = email.message.Message()
        >>> is_json_serializable(msg)
        (False, "object of type 'Message' is not JSON serializable")
    """
    try:
        json.dumps(value, ensure_ascii=True)
        return True, ""
    except (TypeError, ValueError, OverflowError) as e:
        return False, str(e)


def get_object_type_name(value: Any) -> str:
    """
    Get human-readable type name for an object.

    Examples:
        >>> get_object_type_name("hello")
        "str"

        >>> import email
        >>> msg = email.message.Message()
        >>> get_object_type_name(msg)
        "email.message.Message"
    """
    obj_type = type(value)
    module = obj_type.__module__
    name = obj_type.__name__

    if module == 'builtins':
        return name
    return f"{module}.{name}"


def sanitize_value(value: Any, path: str = "root") -> Any:
    """
    Recursively sanitize a value to ensure JSON compatibility.

    Handles:
    - datetime/date → ISO string
    - Decimal → float
    - bytes → base64 string (already handled by workflow code)
    - Complex objects → type info dict
    - Sets → lists

    Args:
        value: Value to sanitize
        path: Current path in object tree (for logging)

    Returns:
        JSON-serializable version of the value
    """
    # Check if already serializable
    is_safe, _ = is_json_serializable(value)
    if is_safe:
        return value

    # Handle common non-serializable types

    # datetime/date → ISO string
    if isinstance(value, (datetime, date)):
        return value.isoformat()

    # Decimal → float
    if isinstance(value, Decimal):
        return float(value)

    # Set → list
    if isinstance(value, set):
        return list(value)

    # Dict → recursively sanitize
    if isinstance(value, dict):
        return {k: sanitize_value(v, f"{path}.{k}") for k, v in value.items()}

    # List/tuple → recursively sanitize
    if isinstance(value, (list, tuple)):
        return [sanitize_value(item, f"{path}[{i}]") for i, item in enumerate(value)]

    # Complex object → replace with metadata
    # This is the key fix: instead of trying to serialize email.Message,
    # we replace it with a dict describing what it was
    type_name = get_object_type_name(value)

    logger.warning(
        f"Context sanitization: Replacing non-serializable object at '{path}' "
        f"(type: {type_name}) with metadata dict"
    )

    # Try to extract useful info from the object
    metadata = {
        "_object_type": type_name,
        "_serialization_error": "Object was not JSON-serializable and was replaced with this metadata",
        "_sanitized_at": datetime.utcnow().isoformat()
    }

    # Try to get string representation (if safe)
    try:
        str_repr = str(value)
        if len(str_repr) < 200:  # Don't store huge strings
            metadata["_str_repr"] = str_repr
    except Exception:
        pass

    # Try to get useful attributes (e.g., for email.Message)
    if hasattr(value, '__dict__'):
        try:
            # Get simple attributes only
            attrs = {}
            for key, val in value.__dict__.items():
                if isinstance(val, SAFE_TYPES):
                    attrs[key] = val
            if attrs:
                metadata["_attributes"] = attrs
        except Exception:
            pass

    return metadata


def sanitize_context(context: Dict[str, Any], strict: bool = False) -> Dict[str, Any]:
    """
    Sanitize context to ensure all values are JSON-serializable.

    This is the LAST line of defense before saving to database.
    Use this in GraphEngine before persisting to chain_of_work.

    Args:
        context: Context dict to sanitize
        strict: If True, raise error instead of sanitizing (for debugging)

    Returns:
        Sanitized context dict (all values JSON-serializable)

    Raises:
        ContextValidationError: If strict=True and context has non-serializable data

    Examples:
        >>> ctx = {"amount": 1200, "email": "test@example.com"}
        >>> sanitize_context(ctx)
        {"amount": 1200, "email": "test@example.com"}

        >>> import email
        >>> msg = email.message.Message()
        >>> ctx = {"msg": msg, "amount": 1200}
        >>> sanitized = sanitize_context(ctx)
        >>> sanitized["amount"]
        1200
        >>> sanitized["msg"]["_object_type"]
        'email.message.Message'
    """
    # First check if sanitization is needed
    is_safe, error = is_json_serializable(context)

    if is_safe:
        return context  # Already clean

    if strict:
        raise ContextValidationError(
            f"Context contains non-serializable data: {error}"
        )

    # Sanitize recursively
    logger.info("Sanitizing context to ensure JSON compatibility")
    sanitized = sanitize_value(context, "context")

    # Verify sanitization worked
    is_safe_now, error = is_json_serializable(sanitized)
    if not is_safe_now:
        # This should never happen, but just in case
        raise ContextValidationError(
            f"Context sanitization failed: {error}. "
            "This is a bug in the sanitizer."
        )

    return sanitized


def validate_context(context: Dict[str, Any]) -> None:
    """
    Validate that context is JSON-serializable.

    Use this in tests or debug mode to catch serialization issues early.

    Args:
        context: Context to validate

    Raises:
        ContextValidationError: If context contains non-serializable data

    Examples:
        >>> validate_context({"amount": 1200})  # OK

        >>> import email
        >>> msg = email.message.Message()
        >>> validate_context({"msg": msg})  # Raises ContextValidationError
    """
    is_safe, error = is_json_serializable(context)

    if not is_safe:
        # Find the problematic keys for better error message
        problematic_keys = []
        for key, value in context.items():
            is_value_safe, _ = is_json_serializable(value)
            if not is_value_safe:
                type_name = get_object_type_name(value)
                problematic_keys.append(f"{key} ({type_name})")

        raise ContextValidationError(
            f"Context validation failed: {error}\n"
            f"Problematic keys: {', '.join(problematic_keys)}\n"
            f"Hint: Use sanitize_context() to auto-clean, or fix the workflow code "
            f"to not store non-serializable objects (email.Message, file handles, etc.)"
        )


def get_context_stats(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get statistics about context for debugging.

    Returns:
        Dict with stats like: total_keys, serializable_keys, problematic_keys, etc.
    """
    total_keys = len(context)
    problematic = []
    serializable = []

    for key, value in context.items():
        is_safe, error = is_json_serializable(value)
        if is_safe:
            serializable.append(key)
        else:
            type_name = get_object_type_name(value)
            problematic.append({
                "key": key,
                "type": type_name,
                "error": error
            })

    return {
        "total_keys": total_keys,
        "serializable_keys": len(serializable),
        "problematic_keys": len(problematic),
        "is_fully_serializable": len(problematic) == 0,
        "problematic_details": problematic
    }
