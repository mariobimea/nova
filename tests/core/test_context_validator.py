"""
Tests for Context Validator & Sanitizer

Tests the system that prevents non-serializable objects from crashing workflows.
"""

import pytest
import json
import email
from datetime import datetime, date
from decimal import Decimal

from src.core.context_validator import (
    sanitize_context,
    validate_context,
    is_json_serializable,
    get_object_type_name,
    get_context_stats,
    ContextValidationError
)


class TestIsJSONSerializable:
    """Test the is_json_serializable checker"""

    def test_safe_primitives(self):
        """Primitives should be serializable"""
        assert is_json_serializable("hello")[0] is True
        assert is_json_serializable(123)[0] is True
        assert is_json_serializable(45.67)[0] is True
        assert is_json_serializable(True)[0] is True
        assert is_json_serializable(None)[0] is True

    def test_safe_collections(self):
        """Simple collections should be serializable"""
        assert is_json_serializable([])[0] is True
        assert is_json_serializable({})[0] is True
        assert is_json_serializable([1, 2, 3])[0] is True
        assert is_json_serializable({"a": 1, "b": 2})[0] is True

    def test_nested_collections(self):
        """Nested collections should be serializable"""
        nested = {"data": [{"id": 1, "values": [10, 20, 30]}]}
        assert is_json_serializable(nested)[0] is True

    def test_email_message_not_serializable(self):
        """email.Message objects should NOT be serializable"""
        msg = email.message.Message()
        is_safe, error = is_json_serializable(msg)
        assert is_safe is False
        assert "Message" in error

    def test_file_handle_not_serializable(self):
        """File handles should NOT be serializable"""
        with open(__file__, 'r') as f:
            is_safe, error = is_json_serializable(f)
            assert is_safe is False


class TestGetObjectTypeName:
    """Test the type name extractor"""

    def test_builtin_types(self):
        """Builtin types should return simple names"""
        assert get_object_type_name("hello") == "str"
        assert get_object_type_name(123) == "int"
        assert get_object_type_name([]) == "list"

    def test_email_message_type(self):
        """email.Message should return full qualified name"""
        msg = email.message.Message()
        type_name = get_object_type_name(msg)
        assert "Message" in type_name
        assert "email" in type_name


class TestSanitizeContext:
    """Test the context sanitizer (main feature)"""

    def test_already_clean_context(self):
        """Clean context should pass through unchanged"""
        ctx = {"amount": 1200, "email": "test@example.com", "valid": True}
        sanitized = sanitize_context(ctx)
        assert sanitized == ctx

    def test_sanitize_email_message_object(self):
        """email.Message should be replaced with metadata"""
        msg = email.message.Message()
        msg['From'] = 'test@example.com'
        msg['Subject'] = 'Test Email'

        ctx = {"email_msg": msg, "amount": 1200}
        sanitized = sanitize_context(ctx)

        # amount should be unchanged
        assert sanitized["amount"] == 1200

        # email_msg should be replaced with metadata dict
        assert isinstance(sanitized["email_msg"], dict)
        assert sanitized["email_msg"]["_object_type"] == "email.message.Message"
        assert "_serialization_error" in sanitized["email_msg"]

    def test_sanitize_datetime(self):
        """datetime should convert to ISO string"""
        now = datetime(2025, 1, 15, 10, 30, 45)
        ctx = {"timestamp": now, "amount": 1200}
        sanitized = sanitize_context(ctx)

        assert sanitized["amount"] == 1200
        assert isinstance(sanitized["timestamp"], str)
        assert "2025-01-15" in sanitized["timestamp"]

    def test_sanitize_date(self):
        """date should convert to ISO string"""
        today = date(2025, 1, 15)
        ctx = {"date": today}
        sanitized = sanitize_context(ctx)

        assert isinstance(sanitized["date"], str)
        assert sanitized["date"] == "2025-01-15"

    def test_sanitize_decimal(self):
        """Decimal should convert to float"""
        amount = Decimal("1234.56")
        ctx = {"amount": amount}
        sanitized = sanitize_context(ctx)

        assert isinstance(sanitized["amount"], float)
        assert sanitized["amount"] == 1234.56

    def test_sanitize_set(self):
        """Set should convert to list"""
        tags = {"python", "workflow", "ai"}
        ctx = {"tags": tags}
        sanitized = sanitize_context(ctx)

        assert isinstance(sanitized["tags"], list)
        assert set(sanitized["tags"]) == tags

    def test_sanitize_nested_dict(self):
        """Nested dicts with complex objects should sanitize recursively"""
        msg = email.message.Message()
        ctx = {
            "data": {
                "email": msg,
                "amount": 1200
            }
        }
        sanitized = sanitize_context(ctx)

        assert sanitized["data"]["amount"] == 1200
        assert isinstance(sanitized["data"]["email"], dict)
        assert sanitized["data"]["email"]["_object_type"] == "email.message.Message"

    def test_sanitize_list_with_complex_objects(self):
        """Lists containing complex objects should sanitize"""
        msg1 = email.message.Message()
        msg2 = email.message.Message()

        ctx = {"messages": [msg1, msg2, "simple_string"]}
        sanitized = sanitize_context(ctx)

        assert len(sanitized["messages"]) == 3
        assert isinstance(sanitized["messages"][0], dict)
        assert isinstance(sanitized["messages"][1], dict)
        assert sanitized["messages"][2] == "simple_string"

    def test_result_is_json_serializable(self):
        """After sanitization, result should be JSON-serializable"""
        msg = email.message.Message()
        ctx = {
            "email": msg,
            "timestamp": datetime.now(),
            "amount": Decimal("1234.56"),
            "tags": {"a", "b", "c"}
        }

        sanitized = sanitize_context(ctx)

        # Should not raise
        json_str = json.dumps(sanitized)
        assert isinstance(json_str, str)

        # Should round-trip correctly
        parsed = json.loads(json_str)
        assert isinstance(parsed, dict)

    def test_strict_mode_raises_error(self):
        """Strict mode should raise error instead of sanitizing"""
        msg = email.message.Message()
        ctx = {"email": msg}

        with pytest.raises(ContextValidationError):
            sanitize_context(ctx, strict=True)


class TestValidateContext:
    """Test the context validator (strict mode)"""

    def test_valid_context_passes(self):
        """Valid context should pass validation"""
        ctx = {"amount": 1200, "email": "test@example.com"}
        validate_context(ctx)  # Should not raise

    def test_invalid_context_raises(self):
        """Invalid context should raise ContextValidationError"""
        msg = email.message.Message()
        ctx = {"email_msg": msg, "amount": 1200}

        with pytest.raises(ContextValidationError) as exc_info:
            validate_context(ctx)

        error_msg = str(exc_info.value)
        assert "email_msg" in error_msg
        assert "Message" in error_msg

    def test_error_message_shows_problematic_keys(self):
        """Error should list all problematic keys"""
        msg = email.message.Message()
        with open(__file__, 'r') as f:
            ctx = {"email_msg": msg, "file": f, "amount": 1200}

            with pytest.raises(ContextValidationError) as exc_info:
                validate_context(ctx)

            error_msg = str(exc_info.value)
            assert "email_msg" in error_msg
            assert "file" in error_msg
            # amount should NOT be in error (it's valid)
            assert "amount" not in error_msg or "1200" not in error_msg


class TestGetContextStats:
    """Test the context statistics helper"""

    def test_fully_clean_context(self):
        """Clean context should show 100% serializable"""
        ctx = {"a": 1, "b": "hello", "c": [1, 2, 3]}
        stats = get_context_stats(ctx)

        assert stats["total_keys"] == 3
        assert stats["serializable_keys"] == 3
        assert stats["problematic_keys"] == 0
        assert stats["is_fully_serializable"] is True

    def test_mixed_context(self):
        """Mixed context should identify problematic keys"""
        msg = email.message.Message()
        ctx = {"email": msg, "amount": 1200, "valid": True}
        stats = get_context_stats(ctx)

        assert stats["total_keys"] == 3
        assert stats["serializable_keys"] == 2  # amount, valid
        assert stats["problematic_keys"] == 1   # email
        assert stats["is_fully_serializable"] is False

        # Check details
        assert len(stats["problematic_details"]) == 1
        assert stats["problematic_details"][0]["key"] == "email"
        assert "Message" in stats["problematic_details"][0]["type"]


class TestRealWorldScenarios:
    """Test real scenarios from Invoice Processing workflow"""

    def test_email_workflow_context(self):
        """Simulate context from email reading node"""
        # This is what the AI-generated code might try to do
        msg = email.message.Message()
        msg['From'] = 'mario@bimea.es'
        msg['Subject'] = 'Invoice #12345'

        ctx = {
            "email_from": "mario@bimea.es",
            "email_subject": "Invoice #12345",
            "email_message_obj": msg,  # ❌ PROBLEM
            "has_emails": True
        }

        # Sanitize should fix it
        sanitized = sanitize_context(ctx)

        # Simple fields preserved
        assert sanitized["email_from"] == "mario@bimea.es"
        assert sanitized["email_subject"] == "Invoice #12345"
        assert sanitized["has_emails"] is True

        # Message object replaced
        assert isinstance(sanitized["email_message_obj"], dict)
        assert sanitized["email_message_obj"]["_object_type"] == "email.message.Message"

        # Result is JSON-serializable
        json.dumps(sanitized)  # Should not raise

    def test_pdf_extraction_context(self):
        """Context after PDF extraction should be clean"""
        ctx = {
            "pdf_data_b64": "base64encodedstring...",
            "pdf_filename": "invoice.pdf",
            "pdf_size_bytes": 45678,
            "has_pdf": True
        }

        # Should pass validation
        validate_context(ctx)

        # Should pass sanitization unchanged
        sanitized = sanitize_context(ctx)
        assert sanitized == ctx
