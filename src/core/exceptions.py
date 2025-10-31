"""
Custom Exceptions for NOVA

This module defines custom exception types for better error handling and retry logic.

Exception Hierarchy:
- NovaException (base)
  - WorkflowError
    - GraphValidationError (don't retry)
    - GraphExecutionError (retry)
  - ExecutorError
    - E2BSandboxError (retry with circuit breaker)
    - E2BTimeoutError (retry)
    - E2BConnectionError (retry)
  - CredentialsError (don't retry)
  - DatabaseError (retry)
"""


class NovaException(Exception):
    """Base exception for all NOVA errors"""

    def __init__(self, message: str, retry_allowed: bool = True):
        super().__init__(message)
        self.message = message
        self.retry_allowed = retry_allowed


# ============================================================================
# WORKFLOW ERRORS
# ============================================================================

class WorkflowError(NovaException):
    """Base class for workflow-related errors"""
    pass


class GraphValidationError(WorkflowError):
    """
    Workflow structure is invalid (e.g., cycles, missing nodes, orphaned nodes).
    Should NOT be retried - fix the workflow definition.
    """

    def __init__(self, message: str):
        super().__init__(message, retry_allowed=False)


class GraphExecutionError(WorkflowError):
    """
    Workflow execution failed (e.g., node execution error, timeout).
    Should be retried.
    """

    def __init__(self, message: str):
        super().__init__(message, retry_allowed=True)


# ============================================================================
# EXECUTOR ERRORS
# ============================================================================

class ExecutorError(NovaException):
    """Base class for executor-related errors"""
    pass


class E2BSandboxError(ExecutorError):
    """
    E2B sandbox error (e.g., code execution failed, sandbox crashed).
    Should be retried with circuit breaker.
    """

    def __init__(self, message: str, sandbox_id: str = None):
        super().__init__(message, retry_allowed=True)
        self.sandbox_id = sandbox_id


class E2BTimeoutError(E2BSandboxError):
    """
    E2B execution timeout (code took too long).
    Should be retried.
    """

    def __init__(self, message: str, timeout_seconds: int = None):
        super().__init__(message)
        self.timeout_seconds = timeout_seconds


class E2BConnectionError(E2BSandboxError):
    """
    E2B connection error (e.g., network issue, API unreachable).
    Should be retried.
    """

    def __init__(self, message: str):
        super().__init__(message)


class CodeExecutionError(ExecutorError):
    """
    User code execution error (e.g., syntax error, runtime error).
    Should NOT be retried - fix the code.
    """

    def __init__(self, message: str, code: str = None, error_details: str = None):
        super().__init__(message, retry_allowed=False)
        self.code = code
        self.error_details = error_details


# ============================================================================
# CREDENTIALS ERRORS
# ============================================================================

class CredentialsError(NovaException):
    """
    Credentials not found or invalid.
    Should NOT be retried - fix the credentials.
    """

    def __init__(self, message: str, client_slug: str = None):
        super().__init__(message, retry_allowed=False)
        self.client_slug = client_slug


# ============================================================================
# DATABASE ERRORS
# ============================================================================

class DatabaseError(NovaException):
    """
    Database connection or query error.
    Should be retried (transient failures).
    """

    def __init__(self, message: str):
        super().__init__(message, retry_allowed=True)


# ============================================================================
# CONTEXT ERRORS
# ============================================================================

class ContextError(NovaException):
    """
    Context-related error (e.g., missing required field, invalid data).
    Should NOT be retried - fix the context or workflow.
    """

    def __init__(self, message: str, context_key: str = None):
        super().__init__(message, retry_allowed=False)
        self.context_key = context_key
