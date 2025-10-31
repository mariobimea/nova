"""
Unit Tests for Custom Exceptions

Tests cover:
- Exception hierarchy
- retry_allowed flag behavior
- Exception attributes
- Error classification
"""

import pytest

from src.core.exceptions import (
    NovaException,
    WorkflowError,
    GraphValidationError,
    GraphExecutionError,
    ExecutorError,
    E2BSandboxError,
    E2BTimeoutError,
    E2BConnectionError,
    CodeExecutionError,
    CredentialsError,
    DatabaseError,
    ContextError
)


# ============================================================================
# BASE EXCEPTION TESTS
# ============================================================================

@pytest.mark.unit
def test_nova_exception_base():
    """Test NovaException base class"""
    exc = NovaException("Test error")

    assert str(exc) == "Test error"
    assert exc.message == "Test error"
    assert exc.retry_allowed == True  # Default


@pytest.mark.unit
def test_nova_exception_no_retry():
    """Test NovaException with retry_allowed=False"""
    exc = NovaException("No retry", retry_allowed=False)

    assert exc.retry_allowed == False


# ============================================================================
# WORKFLOW ERROR TESTS
# ============================================================================

@pytest.mark.unit
def test_graph_validation_error():
    """Test GraphValidationError does not allow retry"""
    exc = GraphValidationError("Invalid graph structure")

    assert isinstance(exc, WorkflowError)
    assert isinstance(exc, NovaException)
    assert exc.retry_allowed == False
    assert "Invalid graph structure" in str(exc)


@pytest.mark.unit
def test_graph_execution_error():
    """Test GraphExecutionError allows retry"""
    exc = GraphExecutionError("Execution failed")

    assert isinstance(exc, WorkflowError)
    assert isinstance(exc, NovaException)
    assert exc.retry_allowed == True
    assert "Execution failed" in str(exc)


# ============================================================================
# EXECUTOR ERROR TESTS
# ============================================================================

@pytest.mark.unit
def test_e2b_sandbox_error():
    """Test E2BSandboxError with sandbox_id"""
    exc = E2BSandboxError("Sandbox crashed", sandbox_id="sbx-123")

    assert isinstance(exc, ExecutorError)
    assert isinstance(exc, NovaException)
    assert exc.retry_allowed == True
    assert exc.sandbox_id == "sbx-123"
    assert "Sandbox crashed" in str(exc)


@pytest.mark.unit
def test_e2b_sandbox_error_no_id():
    """Test E2BSandboxError without sandbox_id"""
    exc = E2BSandboxError("Sandbox error")

    assert exc.sandbox_id is None
    assert exc.retry_allowed == True


@pytest.mark.unit
def test_e2b_timeout_error():
    """Test E2BTimeoutError with timeout_seconds"""
    exc = E2BTimeoutError("Execution timeout", timeout_seconds=60)

    assert isinstance(exc, E2BSandboxError)
    assert isinstance(exc, ExecutorError)
    assert exc.retry_allowed == True
    assert exc.timeout_seconds == 60
    assert "timeout" in str(exc).lower()


@pytest.mark.unit
def test_e2b_connection_error():
    """Test E2BConnectionError"""
    exc = E2BConnectionError("Connection failed")

    assert isinstance(exc, E2BSandboxError)
    assert isinstance(exc, ExecutorError)
    assert exc.retry_allowed == True
    assert "Connection failed" in str(exc)


@pytest.mark.unit
def test_code_execution_error():
    """Test CodeExecutionError does not allow retry"""
    code = "print('hello"  # Syntax error
    exc = CodeExecutionError(
        "Syntax error",
        code=code,
        error_details="SyntaxError: unterminated string"
    )

    assert isinstance(exc, ExecutorError)
    assert exc.retry_allowed == False
    assert exc.code == code
    assert exc.error_details == "SyntaxError: unterminated string"


@pytest.mark.unit
def test_code_execution_error_minimal():
    """Test CodeExecutionError with minimal info"""
    exc = CodeExecutionError("Runtime error")

    assert exc.retry_allowed == False
    assert exc.code is None
    assert exc.error_details is None


# ============================================================================
# CREDENTIALS ERROR TESTS
# ============================================================================

@pytest.mark.unit
def test_credentials_error():
    """Test CredentialsError does not allow retry"""
    exc = CredentialsError("Client not found", client_slug="test-client")

    assert isinstance(exc, NovaException)
    assert exc.retry_allowed == False
    assert exc.client_slug == "test-client"
    assert "Client not found" in str(exc)


@pytest.mark.unit
def test_credentials_error_no_slug():
    """Test CredentialsError without client_slug"""
    exc = CredentialsError("Invalid credentials")

    assert exc.client_slug is None
    assert exc.retry_allowed == False


# ============================================================================
# DATABASE ERROR TESTS
# ============================================================================

@pytest.mark.unit
def test_database_error():
    """Test DatabaseError allows retry"""
    exc = DatabaseError("Connection timeout")

    assert isinstance(exc, NovaException)
    assert exc.retry_allowed == True
    assert "Connection timeout" in str(exc)


# ============================================================================
# CONTEXT ERROR TESTS
# ============================================================================

@pytest.mark.unit
def test_context_error():
    """Test ContextError does not allow retry"""
    exc = ContextError("Missing required field", context_key="user_id")

    assert isinstance(exc, NovaException)
    assert exc.retry_allowed == False
    assert exc.context_key == "user_id"
    assert "Missing required field" in str(exc)


@pytest.mark.unit
def test_context_error_no_key():
    """Test ContextError without context_key"""
    exc = ContextError("Invalid context")

    assert exc.context_key is None
    assert exc.retry_allowed == False


# ============================================================================
# EXCEPTION HIERARCHY TESTS
# ============================================================================

@pytest.mark.unit
def test_exception_hierarchy():
    """Test exception class hierarchy is correct"""
    # All custom exceptions inherit from NovaException
    assert issubclass(WorkflowError, NovaException)
    assert issubclass(ExecutorError, NovaException)
    assert issubclass(CredentialsError, NovaException)
    assert issubclass(DatabaseError, NovaException)
    assert issubclass(ContextError, NovaException)

    # Workflow errors
    assert issubclass(GraphValidationError, WorkflowError)
    assert issubclass(GraphExecutionError, WorkflowError)

    # Executor errors
    assert issubclass(E2BSandboxError, ExecutorError)
    assert issubclass(E2BTimeoutError, E2BSandboxError)
    assert issubclass(E2BConnectionError, E2BSandboxError)
    assert issubclass(CodeExecutionError, ExecutorError)


# ============================================================================
# RETRY CLASSIFICATION TESTS
# ============================================================================

@pytest.mark.unit
def test_retry_allowed_exceptions():
    """Test which exceptions allow retry"""
    retryable = [
        GraphExecutionError("test"),
        E2BSandboxError("test"),
        E2BTimeoutError("test"),
        E2BConnectionError("test"),
        DatabaseError("test"),
    ]

    for exc in retryable:
        assert exc.retry_allowed == True, f"{exc.__class__.__name__} should allow retry"


@pytest.mark.unit
def test_retry_not_allowed_exceptions():
    """Test which exceptions do NOT allow retry"""
    non_retryable = [
        GraphValidationError("test"),
        CodeExecutionError("test"),
        CredentialsError("test"),
        ContextError("test"),
    ]

    for exc in non_retryable:
        assert exc.retry_allowed == False, f"{exc.__class__.__name__} should NOT allow retry"


# ============================================================================
# ERROR CATCHING TESTS
# ============================================================================

@pytest.mark.unit
def test_catch_specific_exception():
    """Test catching specific exception types"""
    try:
        raise E2BTimeoutError("Timeout", timeout_seconds=60)
    except E2BTimeoutError as e:
        assert e.timeout_seconds == 60
    except Exception:
        pytest.fail("Should catch E2BTimeoutError specifically")


@pytest.mark.unit
def test_catch_parent_exception():
    """Test catching by parent class"""
    try:
        raise E2BConnectionError("Connection failed")
    except E2BSandboxError as e:
        # E2BConnectionError inherits from E2BSandboxError
        assert "Connection failed" in str(e)
    except Exception:
        pytest.fail("Should catch by parent class")


@pytest.mark.unit
def test_catch_base_exception():
    """Test catching by base NovaException"""
    try:
        raise CredentialsError("Not found", client_slug="test")
    except NovaException as e:
        # All custom exceptions inherit from NovaException
        assert e.client_slug == "test"
        assert e.retry_allowed == False
    except Exception:
        pytest.fail("Should catch by base NovaException")


# ============================================================================
# EXCEPTION RAISING TESTS
# ============================================================================

@pytest.mark.unit
def test_raise_and_catch_workflow_error():
    """Test raising and catching workflow errors"""
    with pytest.raises(GraphValidationError, match="Invalid structure"):
        raise GraphValidationError("Invalid structure")


@pytest.mark.unit
def test_raise_and_catch_executor_error():
    """Test raising and catching executor errors"""
    with pytest.raises(E2BSandboxError, match="Sandbox crashed"):
        raise E2BSandboxError("Sandbox crashed", sandbox_id="sbx-123")


@pytest.mark.unit
def test_exception_message_formatting():
    """Test exception messages are properly formatted"""
    exc1 = GraphValidationError("Graph has {count} errors".format(count=3))
    assert "Graph has 3 errors" in str(exc1)

    exc2 = E2BTimeoutError(f"Timeout after {60} seconds", timeout_seconds=60)
    assert "Timeout after 60 seconds" in str(exc2)
