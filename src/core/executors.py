"""
Executor System for NOVA Workflow Engine

This module defines execution strategies for workflow nodes:
- ExecutorStrategy: Abstract interface for all executors
- E2BExecutor: Executes code in E2B cloud sandbox (Phase 1 - DEFAULT)
- CachedExecutor: Reuses cached code or generates with AI (Phase 2 - placeholder)
- AIExecutor: Always generates fresh code with LLM (Phase 2 - placeholder)

Executors handle:
1. Context injection (serialize context as JSON, inject into code)
2. Communication with E2B cloud sandbox
3. Result parsing (extract updated context from output)
4. Error handling, timeouts, and circuit breaking
"""

import json
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import logging

from .exceptions import (
    ExecutorError,
    E2BSandboxError,
    E2BTimeoutError,
    E2BConnectionError,
    CodeExecutionError
)
from .circuit_breaker import e2b_circuit_breaker

logger = logging.getLogger(__name__)


class ExecutorStrategy(ABC):
    """
    Abstract interface for all execution strategies.

    All executors must implement the execute() method which:
    - Takes code, context, and timeout
    - Returns updated context after execution
    - Raises ExecutorError on failure
    """

    @abstractmethod
    async def execute(
        self,
        code: str,
        context: Dict[str, Any],
        timeout: int
    ) -> Dict[str, Any]:
        """
        Execute code with given context.

        Args:
            code: Python code to execute
            context: Current workflow context (will be injected)
            timeout: Execution timeout in seconds

        Returns:
            Updated context after execution

        Raises:
            ExecutorError: If execution fails
        """
        pass


class CachedExecutor(ExecutorStrategy):
    """
    Phase 2: Reuses cached successful code or generates with AI if cache miss.

    NOT IMPLEMENTED YET - Placeholder for Phase 2.
    """

    async def execute(
        self,
        code: str,
        context: Dict[str, Any],
        timeout: int
    ) -> Dict[str, Any]:
        raise NotImplementedError("CachedExecutor is Phase 2 feature")


class AIExecutor(ExecutorStrategy):
    """
    Phase 2: Always generates fresh code using LLM.

    NOT IMPLEMENTED YET - Placeholder for Phase 2.
    """

    async def execute(
        self,
        code: str,
        context: Dict[str, Any],
        timeout: int
    ) -> Dict[str, Any]:
        raise NotImplementedError("AIExecutor is Phase 2 feature")


class E2BExecutor(ExecutorStrategy):
    """
    Executes code in E2B cloud sandbox (https://e2b.dev).

    E2B provides isolated Python sandboxes with:
    - Network access (can call APIs, databases, email servers)
    - Pre-installed libraries (requests, pandas, PIL, etc.)
    - Resource limits and timeouts
    - No infrastructure maintenance required

    Similar to Maisa's approach: code executes in a controlled environment
    with full auditability while having access to external services.

    Features:
    - Circuit breaker to prevent overload when E2B is down
    - Automatic retry on transient failures
    - Detailed error classification (timeout, connection, execution)

    Pricing:
    - Hobby tier: $100 free credits (good for ~7 months of development)
    - Usage: ~$0.03/second (2 vCPU + 512MB RAM)
    - Realistic cost: $7-10/month in production

    Requires E2B_API_KEY environment variable.
    Get free API key at: https://e2b.dev/docs
    """

    def __init__(self, api_key: Optional[str] = None, template: Optional[str] = None):
        """
        Initialize E2BExecutor.

        Args:
            api_key: E2B API key (or set E2B_API_KEY env var)
            template: E2B template ID (optional - uses base template if not provided)
        """
        import os
        self.api_key = api_key or os.getenv("E2B_API_KEY")
        self.template = template  # Can be None for base template

        if not self.api_key:
            raise ValueError(
                "E2B API key required. Set E2B_API_KEY environment variable or pass api_key parameter. "
                "Get free key at: https://e2b.dev/docs"
            )

        if self.template:
            logger.info(f"E2BExecutor initialized with custom template: {self.template}")
        else:
            logger.info("E2BExecutor initialized with base template")

    def _inject_context(self, code: str, context: Dict[str, Any]) -> str:
        """
        Inject context into code.

        Args:
            code: Original Python code
            context: Context to inject

        Returns:
            Code with context injection
        """
        # CRITICAL: Use ensure_ascii=True for BOTH injection and output
        # This prevents UnicodeEncodeError in E2B sandbox when context contains
        # special characters like \xa0 (non-breaking space), accented characters, etc.
        # Unicode characters are safely escaped as \uXXXX which works in all environments
        context_json = json.dumps(context, ensure_ascii=True)

        full_code = f"""import json

# Injected context (workflow state)
context = json.loads('''{context_json}''')

# User code
{code}

# Output updated context
# Use ensure_ascii=True to avoid encoding issues with E2B stdout
# Unicode characters will be escaped as \\uXXXX but remain valid JSON
print(json.dumps(context, ensure_ascii=True))
"""
        return full_code

    async def execute(
        self,
        code: str,
        context: Dict[str, Any],
        timeout: int
    ) -> Dict[str, Any]:
        """
        Execute code in E2B cloud sandbox with circuit breaker protection.

        Args:
            code: Python code to execute
            context: Current workflow context
            timeout: Execution timeout in seconds

        Returns:
            Updated context after execution

        Raises:
            E2BConnectionError: If circuit breaker is open or E2B unreachable
            E2BTimeoutError: If execution exceeds timeout
            CodeExecutionError: If user code has syntax/runtime errors
            E2BSandboxError: If sandbox crashes or other E2B error
        """
        # Check circuit breaker BEFORE attempting execution
        if e2b_circuit_breaker.is_open():
            error_msg = (
                f"E2B circuit breaker is OPEN. "
                f"Service experiencing issues. "
                f"State: {e2b_circuit_breaker.get_status()}"
            )
            logger.error(error_msg)
            raise E2BConnectionError(error_msg)

        # Inject context
        full_code = self._inject_context(code, context)

        logger.debug(f"Executing code in E2B sandbox (timeout: {timeout}s)")
        logger.debug(f"Code:\n{code}")
        logger.debug(f"Context keys: {list(context.keys())}")
        logger.debug(f"Circuit breaker state: {e2b_circuit_breaker.state}")

        # Run in executor since E2B v2.x SDK is synchronous
        import asyncio
        loop = asyncio.get_event_loop()

        try:
            result = await loop.run_in_executor(None, self._execute_sync, full_code, timeout)

            # Record success in circuit breaker
            e2b_circuit_breaker.record_success()

            return result

        except (E2BSandboxError, E2BTimeoutError, E2BConnectionError, CodeExecutionError):
            # These are already classified errors, just record failure
            e2b_circuit_breaker.record_failure()
            raise

        except Exception as e:
            # Unexpected error - classify and record
            logger.exception(f"Unexpected E2B error: {e}")
            e2b_circuit_breaker.record_failure()

            # Try to classify the error
            error_str = str(e).lower()
            if "timeout" in error_str:
                raise E2BTimeoutError(f"E2B timeout: {e}", timeout_seconds=timeout)
            elif "connection" in error_str or "network" in error_str:
                raise E2BConnectionError(f"E2B connection error: {e}")
            else:
                raise E2BSandboxError(f"E2B unexpected error: {e}")

    def _execute_sync(self, full_code: str, timeout: int) -> Dict[str, Any]:
        """
        Synchronous execution wrapper for E2B v2.x SDK.

        Args:
            full_code: Code with context injection
            timeout: Execution timeout in seconds

        Returns:
            Updated context dictionary

        Raises:
            E2BConnectionError: Connection/API errors
            E2BTimeoutError: Timeout errors
            CodeExecutionError: User code errors (syntax, runtime)
            E2BSandboxError: Other E2B errors
        """
        from e2b_code_interpreter import Sandbox

        sandbox_id = None

        try:
            # Create sandbox - v2.x API is synchronous
            create_kwargs = {
                "api_key": self.api_key,
                "timeout": 120  # 2 minutes timeout for sandbox creation (custom templates may take longer)
            }
            if self.template:
                create_kwargs["template"] = self.template

            logger.debug("Creating E2B sandbox...")

            try:
                # Use context manager for automatic cleanup
                with Sandbox.create(**create_kwargs) as sandbox:
                    sandbox_id = sandbox.id if hasattr(sandbox, 'id') else "unknown"
                    logger.debug(f"E2B sandbox created: {sandbox_id}")

                    # Execute code with timeout (synchronous in v2.x)
                    logger.debug(f"Executing code in sandbox {sandbox_id} (timeout: {timeout}s)")
                    execution = sandbox.run_code(full_code, timeout=timeout)

                    # Check for errors
                    if execution.error:
                        error_name = execution.error.name if hasattr(execution.error, 'name') else "Error"
                        error_value = execution.error.value if hasattr(execution.error, 'value') else str(execution.error)

                        error_msg = f"{error_name}: {error_value}"

                        logger.error(f"E2B code execution error in sandbox {sandbox_id}: {error_msg}")

                        # Classify user code errors vs sandbox errors
                        if error_name in ("SyntaxError", "NameError", "TypeError", "ValueError", "AttributeError", "KeyError", "IndexError"):
                            # User code error - don't retry
                            raise CodeExecutionError(
                                message=f"Code execution failed: {error_msg}",
                                code=full_code,
                                error_details=error_msg
                            )
                        else:
                            # Sandbox error - retry
                            raise E2BSandboxError(error_msg, sandbox_id=sandbox_id)

                    # Get output from stdout
                    # In v2.x, logs.stdout is a list of strings
                    stdout_lines = []
                    if hasattr(execution, 'logs') and execution.logs:
                        if hasattr(execution.logs, 'stdout'):
                            if isinstance(execution.logs.stdout, list):
                                stdout_lines = [line.strip() for line in execution.logs.stdout if line.strip()]
                            elif isinstance(execution.logs.stdout, str):
                                stdout_lines = [line.strip() for line in execution.logs.stdout.split('\n') if line.strip()]

                    if not stdout_lines:
                        error_msg = f"E2B sandbox {sandbox_id} returned empty output"
                        logger.error(error_msg)
                        raise E2BSandboxError(error_msg, sandbox_id=sandbox_id)

                    # The last line should be our JSON output
                    output = stdout_lines[-1]

                    # Parse updated context
                    try:
                        updated_context = json.loads(output)
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse E2B output as JSON: {output}")
                        if hasattr(execution, 'logs') and execution.logs:
                            logger.error(f"Full stdout: {execution.logs.stdout}")

                        # This is a user code error (didn't print valid JSON)
                        raise CodeExecutionError(
                            message=f"Code output is not valid JSON: {e}",
                            code=full_code,
                            error_details=f"Output: {output}"
                        )

                    logger.debug(f"E2B execution successful in sandbox {sandbox_id}")
                    logger.debug(f"Updated context keys: {list(updated_context.keys())}")

                    return updated_context

            except TimeoutError as e:
                # Sandbox creation or execution timeout
                logger.error(f"E2B timeout: {e}")
                raise E2BTimeoutError(f"E2B timeout after {timeout}s: {e}", timeout_seconds=timeout)

            except ConnectionError as e:
                # Network/connection error
                logger.error(f"E2B connection error: {e}")
                raise E2BConnectionError(f"E2B connection failed: {e}")

        except (E2BConnectionError, E2BTimeoutError, CodeExecutionError, E2BSandboxError):
            # Already classified - re-raise
            raise

        except Exception as e:
            # Unexpected error
            error_msg = f"E2B unexpected error in sandbox {sandbox_id or 'unknown'}: {e}"
            logger.exception(error_msg)

            # Try to classify
            error_str = str(e).lower()
            if "timeout" in error_str:
                raise E2BTimeoutError(error_msg, timeout_seconds=timeout)
            elif "connection" in error_str or "network" in error_str or "api" in error_str:
                raise E2BConnectionError(error_msg)
            else:
                raise E2BSandboxError(error_msg, sandbox_id=sandbox_id)


def get_executor(
    executor_type: str = "e2b",
    api_key: Optional[str] = None,
    **kwargs
) -> ExecutorStrategy:
    """
    Factory function: Creates the appropriate executor based on type.

    NOVA uses E2B cloud sandbox by default for all code execution.
    E2B provides network access, pre-installed libraries, and zero maintenance.

    Args:
        executor_type: Type of executor ("e2b", "cached", "ai"). Default: "e2b"
        api_key: E2B API key (or set E2B_API_KEY env var)
        **kwargs: Additional arguments for specific executors

    Returns:
        Executor instance

    Raises:
        NotImplementedError: If executor type is not available in Phase 1
        ValueError: If required arguments are missing

    Examples:
        >>> # E2B sandbox (default)
        >>> executor = get_executor()
        >>> isinstance(executor, E2BExecutor)
        True

        >>> # E2B with explicit API key
        >>> executor = get_executor("e2b", api_key="e2b_...")
        >>> isinstance(executor, E2BExecutor)
        True
    """
    executors = {
        "e2b": E2BExecutor,
        "cached": CachedExecutor,  # Phase 2
        "ai": AIExecutor,  # Phase 2
    }

    executor_class = executors.get(executor_type)
    if not executor_class:
        raise ValueError(
            f"Unknown executor type: '{executor_type}'. "
            f"Valid types: {list(executors.keys())}"
        )

    # Check Phase 1 limitation (only e2b available)
    if executor_type != "e2b":
        raise NotImplementedError(
            f"Executor '{executor_type}' is a Phase 2 feature. "
            f"Phase 1 uses E2B cloud sandbox exclusively."
        )

    # E2BExecutor requires api_key (or E2B_API_KEY env var)
    # Use base template - dependencies will be installed in runtime if needed
    return E2BExecutor(api_key=api_key)
