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
import os
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
import logging

from .exceptions import (
    ExecutorError,
    E2BSandboxError,
    E2BTimeoutError,
    E2BConnectionError,
    CodeExecutionError
)
from .circuit_breaker import e2b_circuit_breaker
from .context_validator import is_json_serializable, get_context_stats
from .output_validator import auto_validate_output

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
    AI-Powered Executor: Generates Python code dynamically using OpenAI GPT-4o-mini.

    This executor:
    1. Takes a natural language prompt (instead of hardcoded code)
    2. Uses KnowledgeManager to build a complete prompt with integration docs
    3. Generates Python code using OpenAI API
    4. Validates and executes the code in E2B sandbox
    5. Retries up to 3 times with error feedback if generation/execution fails
    6. Returns results with AI metadata (tokens, cost, attempts, etc.)

    Example usage:
        executor = CachedExecutor()
        result = await executor.execute(
            code="Extract total amount from invoice PDF",  # Natural language prompt
            context={"pdf_path": "/tmp/invoice.pdf"},
            timeout=30
        )
        # result = {
        #     "total_amount": "$1,234.56",
        #     "_ai_metadata": {
        #         "model": "gpt-5-mini",
        #         "generated_code": "import fitz\n...",
        #         "tokens_input": 7000,
        #         "tokens_output": 450,
        #         "cost_usd": 0.0012,
        #         "attempts": 1
        #     }
        # }

    Pricing (OpenAI gpt-5-mini):
    - Input: $0.25 / 1M tokens (~$0.0025 per 10K tokens)
    - Output: $2.00 / 1M tokens (~$0.0200 per 10K tokens)
    - Typical cost per generation: $0.002 - $0.005 (affordable!)

    Phase 1 MVP: No cache (generates fresh code every time)
    Phase 2: Hash-based cache + semantic cache with embeddings
    """

    def __init__(self, db_session: Optional[Any] = None, default_model: str = "gpt-4o-mini"):
        """
        Initialize CachedExecutor with Multi-Agent Architecture.

        Args:
            db_session: Optional SQLAlchemy session for cache lookups (Phase 2).
                       Currently unused in Phase 1 (no cache implementation yet).
            default_model: Default model to use if not specified in workflow/node.
                          Defaults to "gpt-4o-mini" (cheapest OpenAI model).

        Requires OPENAI_API_KEY environment variable.
        """
        import os
        from openai import AsyncOpenAI
        from .agents import MultiAgentOrchestrator, InputAnalyzerAgent, DataAnalyzerAgent
        from .agents import CodeGeneratorAgent, CodeValidatorAgent, OutputValidatorAgent
        from .agents import AnalysisValidatorAgent
        from .e2b.executor import E2BExecutor as AgentE2BExecutor
        from .integrations.rag_client import RAGClient

        # Store db_session for future cache implementation (Phase 2)
        self.db_session = db_session

        # Store default model
        self.default_model = default_model

        # Initialize OpenAI client
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable required")

        openai_client = AsyncOpenAI(api_key=api_key)

        # Initialize E2B executor for agents
        # Uses same SDK and custom template as StaticExecutor for consistency
        template_id = os.getenv("E2B_TEMPLATE_ID")
        e2b_executor = AgentE2BExecutor(
            api_key=os.getenv("E2B_API_KEY"),
            template=template_id
        )

        # Initialize RAG client (optional - for doc search)
        rag_client = None
        rag_url = os.getenv("RAG_SERVICE_URL")
        if rag_url:
            try:
                rag_client = RAGClient(base_url=rag_url)
                logger.info(f"RAGClient initialized with URL: {rag_url}")
            except Exception as e:
                logger.warning(f"Failed to initialize RAGClient: {e}. Tool calling will be disabled.")
        else:
            logger.warning("RAG_SERVICE_URL not set. Tool calling for doc search will be disabled.")

        # Initialize all agents
        input_analyzer = InputAnalyzerAgent(openai_client)
        data_analyzer = DataAnalyzerAgent(openai_client, e2b_executor)
        code_generator = CodeGeneratorAgent(openai_client, rag_client)  # Pass RAG client
        code_validator = CodeValidatorAgent()
        output_validator = OutputValidatorAgent(openai_client)
        analysis_validator = AnalysisValidatorAgent(openai_client)

        # Initialize Multi-Agent Orchestrator
        self.orchestrator = MultiAgentOrchestrator(
            input_analyzer=input_analyzer,
            data_analyzer=data_analyzer,
            code_generator=code_generator,
            code_validator=code_validator,
            output_validator=output_validator,
            analysis_validator=analysis_validator,
            e2b_executor=e2b_executor,
            max_retries=3
        )

        logger.info(f"CachedExecutor initialized with Multi-Agent Architecture (model: {default_model})")

    async def execute(
        self,
        code: str,  # In CachedExecutor, this is the PROMPT (natural language)
        context: Dict[str, Any],
        timeout: int,
        workflow: Optional[Dict[str, Any]] = None,
        node: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute workflow node using Multi-Agent Architecture.

        This method uses the orchestrator to coordinate all agents:
        1. InputAnalyzer: Decides strategy
        2. DataAnalyzer: Analyzes data if needed
        3. CodeGenerator: Generates Python code (with retries)
        4. CodeValidator: Validates code before execution
        5. E2B: Executes code in sandbox
        6. OutputValidator: Validates results after execution

        The 'code' parameter is treated as a natural language PROMPT.

        Args:
            code: Natural language prompt/task description (NOT Python code)
            context: Current workflow context
            timeout: Execution timeout in seconds (for E2B)
            workflow: Optional workflow dictionary (unused in multi-agent)
            node: Optional node dictionary (unused in multi-agent)

        Returns:
            Updated context with AI metadata from all agents:
            {
                ...context updates from execution...,
                "_ai_metadata": {
                    "input_analysis": {...},
                    "data_analysis": {...},
                    "code_generation": {...},
                    "code_validation": {...},
                    "output_validation": {...},
                    "attempts": 1-3,
                    "errors": [...],
                    "timings": {...}
                }
            }

        Raises:
            ExecutorError: If execution fails after max retries
        """
        prompt_task = code  # 'code' parameter is actually the prompt

        logger.info(f"🚀 CachedExecutor executing with Multi-Agent Architecture")
        logger.info(f"   Task: {prompt_task[:100]}...")
        logger.info(f"   Context keys: {list(context.keys())}")
        logger.info(f"   Timeout: {timeout}s")

        try:
            # Extract node_type from node dict if available
            node_type = None
            if node and isinstance(node, dict):
                node_type = node.get("type")
                logger.info(f"   Node type: {node_type}")

            # Execute workflow using orchestrator
            result = await self.orchestrator.execute_workflow(
                task=prompt_task,
                context=context,
                timeout=timeout,
                node_type=node_type  # Pass node type to orchestrator
            )

            logger.info(f"✅ Multi-Agent execution completed successfully")
            return result

        except Exception as e:
            logger.error(f"❌ Multi-Agent execution failed: {e}")
            raise ExecutorError(f"Multi-Agent execution failed: {e}")


class AIExecutor(ExecutorStrategy):
    """
    Phase 2: Always generates fresh code using LLM.

    NOT IMPLEMENTED YET - Placeholder for Phase 2.
    """

    async def execute(
        self,
        code: str,
        context: Dict[str, Any],
        timeout: int,
        workflow: Optional[Dict[str, Any]] = None,
        node: Optional[Dict[str, Any]] = None
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

        # Escape the JSON string for safe embedding in Python code
        # Replace single quotes and backslashes to avoid breaking the Python string literal
        # This ensures the JSON can contain ANY characters including newlines, quotes, etc.
        escaped_json = context_json.replace('\\', '\\\\').replace("'", "\\'")

        # Check if code already has a print statement
        # AI-generated code (from CachedExecutor) already includes print(json.dumps(...))
        # So we should NOT add another print statement
        has_print = 'print(' in code and 'json.dumps' in code

        if has_print:
            # Code already prints output - just inject context
            full_code = f"""import json

# Injected context (workflow state)
context = json.loads('{escaped_json}')

# User code (already includes output print)
{code}
"""
        else:
            # Code doesn't print - add print statement for E2B
            full_code = f"""import json

# Injected context (workflow state)
context = json.loads('{escaped_json}')

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
        timeout: int,
        workflow: Optional[Dict[str, Any]] = None,
        node: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute code in E2B cloud sandbox with circuit breaker protection.

        Args:
            code: Python code to execute
            context: Current workflow context
            timeout: Execution timeout in seconds
            workflow: Optional workflow definition (unused by E2BExecutor)
            node: Optional node definition (unused by E2BExecutor)

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
        from e2b import Sandbox

        sandbox_id = None
        sandbox = None

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
                # Create sandbox (not using context manager to have better error handling)
                sandbox = Sandbox.create(**create_kwargs)
                sandbox_id = sandbox.id if hasattr(sandbox, 'id') else "unknown"
                logger.debug(f"E2B sandbox created: {sandbox_id}")

                # Execute code using commands.run() instead of run_code()
                logger.debug(f"Executing code in sandbox {sandbox_id} (timeout: {timeout}s)")

                # Write code to a temp file and execute it
                # This avoids issues with quotes and special characters
                import tempfile
                code_file = f"/tmp/nova_code_{sandbox_id}.py"

                # Upload code to sandbox
                sandbox.files.write(code_file, full_code)

                # Execute the file
                execution = sandbox.commands.run(f"python3 {code_file}", timeout=timeout)

                # Check for errors (commands.run returns exit_code, stdout, stderr)
                if execution.exit_code != 0:
                    error_msg = execution.stderr or "Unknown error"

                    logger.error(f"E2B code execution error in sandbox {sandbox_id}: {error_msg}")

                    # Classify user code errors vs sandbox errors
                    if any(err in error_msg for err in ["SyntaxError", "NameError", "TypeError", "ValueError", "AttributeError", "KeyError", "IndexError"]):
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
                stdout_output = execution.stdout or ""
                stdout_lines = [line.strip() for line in stdout_output.split('\n') if line.strip()]

                if not stdout_lines:
                    error_msg = f"E2B sandbox {sandbox_id} returned empty output"
                    logger.error(error_msg)
                    raise E2BSandboxError(error_msg, sandbox_id=sandbox_id)

                # Filter out empty JSON objects from stdout_lines
                # Sometimes AI-generated code adds print(json.dumps(context)) which prints {}
                valid_lines = []
                for line in stdout_lines:
                    # Skip empty JSON objects
                    if line.strip() in ['{}', '[]', 'null']:
                        continue
                    valid_lines.append(line)

                if not valid_lines:
                    error_msg = f"E2B sandbox {sandbox_id} returned only empty JSON"
                    logger.error(error_msg)
                    raise E2BSandboxError(error_msg, sandbox_id=sandbox_id)

                # The last VALID line should be our JSON output
                output = valid_lines[-1]

                # Parse updated context
                try:
                    output_json = json.loads(output)
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse E2B output as JSON: {output}")
                    logger.error(f"Full stdout: {stdout_output}")

                    # This is a user code error (didn't print valid JSON)
                    raise CodeExecutionError(
                        message=f"Code output is not valid JSON: {e}",
                        code=full_code,
                        error_details=f"Output: {output}"
                    )

                # Check if output has the expected structure: {status, context_updates, message}
                # If it does, extract context_updates. Otherwise, use the whole JSON as context.
                if isinstance(output_json, dict) and "context_updates" in output_json:
                    # AI-generated code format: {status, context_updates, message}
                    status = output_json.get("status")
                    message = output_json.get("message")

                    # If status is "error", treat it as a code execution error
                    # This allows the AI to communicate errors gracefully (e.g., "no emails found")
                    # and triggers retry with error feedback
                    if status == "error":
                        logger.warning(f"Code reported error status: {message}")
                        raise CodeExecutionError(
                            message=f"Code execution error: {message}",
                            code=full_code,
                            error_details=message
                        )

                    # Extract context updates and MERGE with original context
                    # CRITICAL: Only return the updates, NOT the full merged context
                    # The orchestrator will handle merging in context_state.current
                    context_updates = output_json.get("context_updates", {})
                    updated_context = context_updates

                    # Log successful execution
                    if status:
                        logger.debug(f"Execution status: {status}")
                    if message:
                        logger.debug(f"Execution message: {message}")
                else:
                    # Legacy format or direct context update
                    updated_context = output_json

                logger.debug(f"E2B execution successful in sandbox {sandbox_id}")
                logger.debug(f"Updated context keys: {list(updated_context.keys())}")

                # Kill sandbox
                sandbox.kill()

                return updated_context

            except TimeoutError as e:
                # Sandbox creation or execution timeout
                logger.error(f"E2B timeout: {e}")
                if sandbox:
                    try:
                        sandbox.kill()
                    except:
                        pass
                raise E2BTimeoutError(f"E2B timeout after {timeout}s: {e}", timeout_seconds=timeout)

            except ConnectionError as e:
                # Network/connection error
                logger.error(f"E2B connection error: {e}")
                if sandbox:
                    try:
                        sandbox.kill()
                    except:
                        pass
                raise E2BConnectionError(f"E2B connection failed: {e}")

        except (E2BConnectionError, E2BTimeoutError, CodeExecutionError, E2BSandboxError):
            # Already classified - clean up sandbox and re-raise
            if sandbox:
                try:
                    sandbox.kill()
                except:
                    pass
            raise

        except Exception as e:
            # Unexpected error
            error_msg = f"E2B unexpected error in sandbox {sandbox_id or 'unknown'}: {e}"
            logger.exception(error_msg)

            # Clean up sandbox
            if sandbox:
                try:
                    sandbox.kill()
                except:
                    pass

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
    db_session: Optional[Any] = None,
    **kwargs
) -> ExecutorStrategy:
    """
    Factory function: Creates the appropriate executor based on type.

    NOVA uses E2B cloud sandbox by default for all code execution.
    E2B provides network access, pre-installed libraries, and zero maintenance.

    Args:
        executor_type: Type of executor ("e2b", "cached", "ai"). Default: "e2b"
        api_key: E2B API key (or set E2B_API_KEY env var)
        db_session: Optional SQLAlchemy session (required for "cached" executor cache in Phase 2)
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

        >>> # Cached executor with AI code generation
        >>> executor = get_executor("cached", db_session=session)
        >>> isinstance(executor, CachedExecutor)
        True
    """
    executors = {
        "e2b": E2BExecutor,
        "cached": CachedExecutor,  # AI-powered code generation (Phase 1+)
        "ai": AIExecutor,  # Future: Always fresh generation (Phase 2)
    }

    executor_class = executors.get(executor_type)
    if not executor_class:
        raise ValueError(
            f"Unknown executor type: '{executor_type}'. "
            f"Valid types: {list(executors.keys())}"
        )

    # Check Phase 2 limitation (AIExecutor not available yet)
    if executor_type == "ai":
        raise NotImplementedError(
            f"Executor '{executor_type}' is a Phase 2 feature. "
            f"Use 'cached' executor for AI-powered code generation."
        )

    # Create executor based on type
    if executor_type == "e2b":
        # E2BExecutor requires api_key (or E2B_API_KEY env var)
        # Use custom template with pre-installed packages for faster cold starts
        # Template: nova-workflow-fresh (wzqi57u2e8v2f90t6lh5)
        # Pre-installed: PyMuPDF, pandas, requests, pillow, psycopg2-binary, python-dotenv
        # IMPORTANT: Ensure E2B_TEMPLATE_ID is set in BOTH API and Worker services (Railway)
        template_id = os.getenv("E2B_TEMPLATE_ID", None)
        return E2BExecutor(api_key=api_key, template=template_id)

    elif executor_type == "cached":
        # CachedExecutor uses OpenAI for code generation + E2B for execution
        # Requires OPENAI_API_KEY environment variable
        # db_session optional (will be used for cache in Phase 2)
        return CachedExecutor(db_session=db_session)

    else:
        # Should never reach here (we check executor_class above)
        raise ValueError(f"Unknown executor type: '{executor_type}'")
