"""
Tests for Executor System

Tests cover:
- StaticExecutor context injection
- StaticExecutor HTTP communication (mocked)
- Error handling (timeouts, HTTP errors, invalid JSON)
- Factory function (get_executor)
- Phase 2 executors (placeholders)
"""

import pytest
import json
from unittest.mock import AsyncMock, patch, Mock
import httpx

from src.core.executors import (
    ExecutorStrategy,
    StaticExecutor,
    CachedExecutor,
    AIExecutor,
    ExecutionError,
    get_executor,
)


# =============================================================================
# StaticExecutor - Context Injection Tests
# =============================================================================


def test_static_executor_initialization():
    """Test StaticExecutor initializes with sandbox URL"""
    executor = StaticExecutor(sandbox_url="http://188.245.183.74:8000")
    assert executor.sandbox_url == "http://188.245.183.74:8000"


def test_static_executor_strips_trailing_slash():
    """Test that trailing slash is removed from URL"""
    executor = StaticExecutor(sandbox_url="http://188.245.183.74:8000/")
    assert executor.sandbox_url == "http://188.245.183.74:8000"


def test_context_injection_simple():
    """Test context injection with simple context"""
    executor = StaticExecutor(sandbox_url="http://test.com")
    code = "total = amount * 1.21"
    context = {"amount": 1000}

    full_code = executor._inject_context(code, context)

    assert "import json" in full_code
    assert '"amount": 1000' in full_code
    assert "total = amount * 1.21" in full_code
    assert "print(json.dumps(context))" in full_code


def test_context_injection_nested():
    """Test context injection with nested objects"""
    executor = StaticExecutor(sandbox_url="http://test.com")
    code = "invoice_data['total'] = calculate_total()"
    context = {
        "invoice_data": {
            "amount": 1200,
            "vendor": "ACME",
            "items": ["item1", "item2"]
        }
    }

    full_code = executor._inject_context(code, context)

    # Check that nested structure is preserved
    assert '"invoice_data"' in full_code
    assert '"amount": 1200' in full_code
    assert '"vendor": "ACME"' in full_code
    assert "item1" in full_code


def test_context_injection_empty_context():
    """Test context injection with empty context"""
    executor = StaticExecutor(sandbox_url="http://test.com")
    code = "x = 1"
    context = {}

    full_code = executor._inject_context(code, context)

    assert "context = {}" in full_code
    assert "x = 1" in full_code


def test_context_injection_special_characters():
    """Test context injection with special characters (quotes, newlines)"""
    executor = StaticExecutor(sandbox_url="http://test.com")
    code = "name = 'John'"
    context = {"description": 'Quote: "hello"', "text": "Line1\nLine2"}

    full_code = executor._inject_context(code, context)

    # Should serialize correctly without breaking JSON
    assert "import json" in full_code
    # Context should be valid JSON
    # Extract context line to validate
    lines = full_code.split("\n")
    context_line = [l for l in lines if l.startswith("context = ")][0]
    # Should be parseable
    extracted_context = json.loads(context_line.replace("context = ", ""))
    assert extracted_context["description"] == 'Quote: "hello"'
    assert extracted_context["text"] == "Line1\nLine2"


# =============================================================================
# StaticExecutor - Execution Tests (Mocked HTTP)
# =============================================================================


@pytest.mark.asyncio
async def test_execute_success():
    """Test successful code execution"""
    executor = StaticExecutor(sandbox_url="http://test.com")

    # Mock HTTP response
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "status": "success",
        "output": '{"amount": 1000, "total": 1210}',
        "execution_time": 0.123
    }

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)

        result = await executor.execute(
            code="total = amount * 1.21",
            context={"amount": 1000},
            timeout=10
        )

    assert result == {"amount": 1000, "total": 1210}


@pytest.mark.asyncio
async def test_execute_http_error():
    """Test handling of HTTP error (non-200 status)"""
    executor = StaticExecutor(sandbox_url="http://test.com")

    mock_response = Mock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)

        with pytest.raises(ExecutionError, match="Sandbox returned status 500"):
            await executor.execute(
                code="x = 1",
                context={},
                timeout=10
            )


@pytest.mark.asyncio
async def test_execute_execution_failed():
    """Test handling of execution failure (status != success)"""
    executor = StaticExecutor(sandbox_url="http://test.com")

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "status": "error",
        "error": "NameError: name 'undefined' is not defined"
    }

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)

        with pytest.raises(ExecutionError, match="Code execution failed"):
            await executor.execute(
                code="result = undefined",
                context={},
                timeout=10
            )


@pytest.mark.asyncio
async def test_execute_invalid_json_output():
    """Test handling of invalid JSON in output"""
    executor = StaticExecutor(sandbox_url="http://test.com")

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "status": "success",
        "output": "This is not JSON"
    }

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)

        with pytest.raises(ExecutionError, match="Invalid JSON in output"):
            await executor.execute(
                code="print('hello')",
                context={},
                timeout=10
            )


@pytest.mark.asyncio
async def test_execute_empty_output():
    """Test handling of empty output"""
    executor = StaticExecutor(sandbox_url="http://test.com")

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "status": "success",
        "output": ""
    }

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)

        with pytest.raises(ExecutionError, match="empty output"):
            await executor.execute(
                code="x = 1",
                context={},
                timeout=10
            )


@pytest.mark.asyncio
async def test_execute_timeout():
    """Test handling of execution timeout"""
    executor = StaticExecutor(sandbox_url="http://test.com")

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(
            side_effect=httpx.TimeoutException("Request timed out")
        )

        with pytest.raises(ExecutionError, match="timed out after 10s"):
            await executor.execute(
                code="import time; time.sleep(100)",
                context={},
                timeout=10
            )


@pytest.mark.asyncio
async def test_execute_connection_error():
    """Test handling of connection error"""
    executor = StaticExecutor(sandbox_url="http://unreachable.com")

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(
            side_effect=httpx.RequestError("Connection refused")
        )

        with pytest.raises(ExecutionError, match="Failed to connect"):
            await executor.execute(
                code="x = 1",
                context={},
                timeout=10
            )


@pytest.mark.asyncio
async def test_execute_timeout_buffer():
    """Test that HTTP timeout has 5s buffer over execution timeout"""
    executor = StaticExecutor(sandbox_url="http://test.com")

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "status": "success",
        "output": '{"result": "ok"}'
    }

    with patch("httpx.AsyncClient") as mock_client:
        mock_post = AsyncMock(return_value=mock_response)
        mock_client.return_value.__aenter__.return_value.post = mock_post

        await executor.execute(
            code="x = 1",
            context={},
            timeout=10
        )

        # Check that HTTP timeout was 15s (10s + 5s buffer)
        call_args = mock_post.call_args
        assert call_args.kwargs["timeout"] == 15


@pytest.mark.asyncio
async def test_execute_sends_correct_payload():
    """Test that execute sends correct payload to sandbox"""
    executor = StaticExecutor(sandbox_url="http://test.com")

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "status": "success",
        "output": '{"result": 42}'
    }

    with patch("httpx.AsyncClient") as mock_client:
        mock_post = AsyncMock(return_value=mock_response)
        mock_client.return_value.__aenter__.return_value.post = mock_post

        await executor.execute(
            code="result = 40 + 2",
            context={"initial": "value"},
            timeout=15
        )

        # Check payload
        call_args = mock_post.call_args
        payload = call_args.kwargs["json"]

        assert payload["timeout"] == 15
        assert "result = 40 + 2" in payload["code"]
        assert '"initial": "value"' in payload["code"]


# =============================================================================
# Phase 2 Executors Tests (Placeholders)
# =============================================================================


@pytest.mark.asyncio
async def test_cached_executor_not_implemented():
    """Test that CachedExecutor raises NotImplementedError"""
    executor = CachedExecutor()
    with pytest.raises(NotImplementedError, match="Phase 2 feature"):
        await executor.execute(code="x=1", context={}, timeout=10)


@pytest.mark.asyncio
async def test_ai_executor_not_implemented():
    """Test that AIExecutor raises NotImplementedError"""
    executor = AIExecutor()
    with pytest.raises(NotImplementedError, match="Phase 2 feature"):
        await executor.execute(code="x=1", context={}, timeout=10)


# =============================================================================
# Factory Function Tests
# =============================================================================


def test_get_executor_static():
    """Test factory creates StaticExecutor"""
    executor = get_executor("static", sandbox_url="http://test.com")
    assert isinstance(executor, StaticExecutor)
    assert executor.sandbox_url == "http://test.com"


def test_get_executor_static_missing_url():
    """Test that StaticExecutor requires sandbox_url"""
    with pytest.raises(ValueError, match="requires 'sandbox_url'"):
        get_executor("static")


def test_get_executor_unknown_type():
    """Test that unknown executor type raises error"""
    with pytest.raises(ValueError, match="Unknown executor type"):
        get_executor("mystery", sandbox_url="http://test.com")


def test_get_executor_phase2_cached():
    """Test that Phase 2 executors raise NotImplementedError"""
    with pytest.raises(NotImplementedError, match="Phase 2 feature"):
        get_executor("cached", sandbox_url="http://test.com")


def test_get_executor_phase2_ai():
    """Test that Phase 2 executors raise NotImplementedError"""
    with pytest.raises(NotImplementedError, match="Phase 2 feature"):
        get_executor("ai", sandbox_url="http://test.com")


# =============================================================================
# Integration Tests
# =============================================================================


@pytest.mark.asyncio
async def test_execute_with_context_updates():
    """Test that context updates are correctly returned"""
    executor = StaticExecutor(sandbox_url="http://test.com")

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "status": "success",
        "output": json.dumps({
            "invoice_data": {"amount": 1200, "vendor": "ACME"},
            "total_with_tax": 1452,
            "status": "processed"
        })
    }

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)

        result = await executor.execute(
            code="""
invoice_data = context.get('invoice_data', {})
total = invoice_data['amount'] * 1.21
context['total_with_tax'] = int(total)
context['status'] = 'processed'
""",
            context={"invoice_data": {"amount": 1200, "vendor": "ACME"}},
            timeout=10
        )

    assert result["total_with_tax"] == 1452
    assert result["status"] == "processed"
    assert result["invoice_data"]["vendor"] == "ACME"


@pytest.mark.asyncio
async def test_execute_decision_node_pattern():
    """Test execution pattern for DecisionNode (writes boolean)"""
    executor = StaticExecutor(sandbox_url="http://test.com")

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "status": "success",
        "output": json.dumps({
            "invoice_data": {"amount": 1500},
            "needs_approval": True
        })
    }

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)

        result = await executor.execute(
            code="""
amount = invoice_data['amount']
context['needs_approval'] = amount > 1000
""",
            context={"invoice_data": {"amount": 1500}},
            timeout=10
        )

    assert result["needs_approval"] is True
    assert isinstance(result["needs_approval"], bool)
