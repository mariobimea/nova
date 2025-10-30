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
4. Error handling and timeouts
"""

import json
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class ExecutionError(Exception):
    """Raised when code execution fails in the sandbox"""
    pass


class ExecutorStrategy(ABC):
    """
    Abstract interface for all execution strategies.

    All executors must implement the execute() method which:
    - Takes code, context, and timeout
    - Returns updated context after execution
    - Raises ExecutionError on failure
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
            ExecutionError: If execution fails
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
        Inject context into code (same as StaticExecutor).

        Args:
            code: Original Python code
            context: Context to inject

        Returns:
            Code with context injection
        """
        # Use ensure_ascii=False for context injection to preserve UTF-8 characters
        context_json = json.dumps(context, ensure_ascii=False)

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
        Execute code in E2B cloud sandbox.

        Args:
            code: Python code to execute
            context: Current workflow context
            timeout: Execution timeout in seconds

        Returns:
            Updated context after execution

        Raises:
            ExecutionError: If execution fails
        """
        from e2b_code_interpreter import Sandbox
        import asyncio

        # Inject context
        full_code = self._inject_context(code, context)

        logger.debug(f"Executing code in E2B sandbox (timeout: {timeout}s)")
        logger.debug(f"Code:\n{code}")
        logger.debug(f"Context: {context}")

        # Run in executor since E2B v2.x SDK is synchronous
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._execute_sync, full_code, timeout)

    def _execute_sync(self, full_code: str, timeout: int) -> Dict[str, Any]:
        """
        Synchronous execution wrapper for E2B v2.x SDK.

        Args:
            full_code: Code with context injection
            timeout: Execution timeout in seconds

        Returns:
            Updated context dictionary

        Raises:
            ExecutionError: If execution fails
        """
        from e2b_code_interpreter import Sandbox

        try:
            # Create sandbox - v2.x API is synchronous
            create_kwargs = {
                "api_key": self.api_key,
                "timeout": 120  # 2 minutes timeout for sandbox creation (custom templates may take longer)
            }
            if self.template:
                create_kwargs["template"] = self.template

            # Use context manager for automatic cleanup
            with Sandbox.create(**create_kwargs) as sandbox:
                # Execute code with timeout (synchronous in v2.x)
                execution = sandbox.run_code(full_code, timeout=timeout)

                # Check for errors
                if execution.error:
                    error_msg = f"E2B execution error: {execution.error.name} - {execution.error.value}"
                    logger.error(error_msg)
                    raise ExecutionError(error_msg)

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
                    raise ExecutionError("E2B sandbox returned empty output")

                # The last line should be our JSON output
                output = stdout_lines[-1]

                # Parse updated context
                try:
                    updated_context = json.loads(output)
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse E2B output as JSON: {output}")
                    if hasattr(execution, 'logs') and execution.logs:
                        logger.error(f"Full stdout: {execution.logs.stdout}")
                    raise ExecutionError(f"Invalid JSON in output: {e}")

                logger.debug(f"E2B execution successful. Updated context: {updated_context}")
                return updated_context

        except Exception as e:
            if isinstance(e, ExecutionError):
                raise

            error_msg = f"E2B sandbox error: {e}"
            logger.error(error_msg)
            raise ExecutionError(error_msg)


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