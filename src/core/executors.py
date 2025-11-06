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
from .context_validator import is_json_serializable, get_context_stats

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
        #         "model": "gpt-4o-mini",
        #         "generated_code": "import fitz\n...",
        #         "tokens_input": 7000,
        #         "tokens_output": 450,
        #         "cost_usd": 0.0012,
        #         "attempts": 1
        #     }
        # }

    Pricing (OpenAI gpt-4o-mini):
    - Input: $0.15 / 1M tokens (~$0.0015 per 10K tokens)
    - Output: $0.60 / 1M tokens (~$0.0060 per 10K tokens)
    - Typical cost per generation: $0.001 - $0.002 (very cheap!)

    Phase 1 MVP: No cache (generates fresh code every time)
    Phase 2: Hash-based cache + semantic cache with embeddings
    """

    def __init__(self, db_session: Optional[Any] = None):
        """
        Initialize CachedExecutor.

        Args:
            db_session: Optional SQLAlchemy session for cache lookups (Phase 2).
                       Currently unused in Phase 1 (no cache implementation yet).

        Requires OPENAI_API_KEY environment variable.
        """
        import os
        from .ai.knowledge_manager import KnowledgeManager

        # Store db_session for future cache implementation (Phase 2)
        self.db_session = db_session

        # Initialize OpenAI client
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY environment variable is required for CachedExecutor. "
                "Get API key at: https://platform.openai.com/api-keys"
            )

        try:
            import openai
            self.openai_client = openai.OpenAI(api_key=api_key)
        except ImportError:
            raise ImportError(
                "OpenAI library not installed. Install with: pip install openai"
            )

        # Initialize E2B executor (for code execution)
        # Use custom template if E2B_TEMPLATE_ID is set
        template_id = os.getenv("E2B_TEMPLATE_ID")
        self.e2b_executor = E2BExecutor(template=template_id)

        # Initialize Knowledge Manager (for prompt building)
        self.knowledge_manager = KnowledgeManager()

        logger.info("CachedExecutor initialized with OpenAI gpt-4o-mini")

    def _clean_code_blocks(self, code: str) -> str:
        """
        Remove markdown code blocks and explanations from AI-generated code.

        OpenAI often wraps code in ```python ... ``` blocks and adds
        explanatory text before/after. This function extracts just the code.

        Args:
            code: Raw output from OpenAI API

        Returns:
            Clean Python code without markdown or explanations
        """
        import re

        # Remove markdown code blocks
        # Pattern: ```python\ncode\n``` or ```\ncode\n```
        code_block_pattern = r'```(?:python)?\s*\n(.*?)\n```'
        matches = re.findall(code_block_pattern, code, re.DOTALL)

        if matches:
            # Take the first code block
            code = matches[0]

        # Remove common explanatory phrases at start/end
        lines = code.split('\n')
        cleaned_lines = []

        for line in lines:
            stripped = line.strip().lower()

            # Skip explanation lines
            if any(phrase in stripped for phrase in [
                "here's the code",
                "here is the code",
                "this code will",
                "the code above",
                "explanation:",
                "note:",
            ]):
                continue

            cleaned_lines.append(line)

        return '\n'.join(cleaned_lines).strip()

    def _validate_syntax(self, code: str) -> None:
        """
        Validate Python syntax using ast.parse().

        Args:
            code: Python code to validate

        Raises:
            CodeExecutionError: If syntax is invalid
        """
        import ast

        try:
            ast.parse(code)
        except SyntaxError as e:
            raise CodeExecutionError(
                message=f"Generated code has invalid syntax: {e}",
                code=code,
                error_details=str(e)
            )

    def _estimate_tokens(self, prompt: str, code: str) -> Dict[str, Any]:
        """
        Estimate token usage and cost.

        Uses simple estimation: ~4 characters = 1 token
        (Actual tokenization is more complex, but this is close enough)

        OpenAI gpt-4o-mini pricing (as of Nov 2024):
        - Input: $0.15 / 1M tokens
        - Output: $0.60 / 1M tokens

        Args:
            prompt: Input prompt sent to OpenAI
            code: Generated code from OpenAI

        Returns:
            Dictionary with token counts and estimated cost
        """
        # Simple estimation: ~4 chars per token
        input_tokens = len(prompt) // 4
        output_tokens = len(code) // 4

        # gpt-4o-mini pricing (per 1M tokens)
        input_cost_per_1m = 0.15
        output_cost_per_1m = 0.60

        # Calculate cost in USD
        input_cost = (input_tokens / 1_000_000) * input_cost_per_1m
        output_cost = (output_tokens / 1_000_000) * output_cost_per_1m
        total_cost = input_cost + output_cost

        return {
            "tokens_input": input_tokens,
            "tokens_output": output_tokens,
            "tokens_total": input_tokens + output_tokens,
            "cost_usd": round(total_cost, 6)  # Round to 6 decimals ($0.000001)
        }

    async def _generate_code(self, prompt: str) -> str:
        """
        Generate Python code using OpenAI API.

        Args:
            prompt: Complete prompt with task, context, and integration docs

        Returns:
            Generated Python code (cleaned and validated)

        Raises:
            ExecutorError: If OpenAI API fails or code generation fails
        """
        import time

        try:
            logger.debug("Calling OpenAI API to generate code...")
            start_time = time.time()

            # Call OpenAI API
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a Python code generator for the NOVA workflow engine. "
                            "Generate clean, executable Python code based on the documentation and task provided. "
                            "IMPORTANT: The code MUST end with EXACTLY ONE print() statement that outputs JSON. "
                            "Do NOT print multiple times. Do NOT print empty JSON at the end. "
                            "Return ONLY the Python code, no explanations or markdown."
                        )
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.2,  # Low temperature for deterministic output
                max_tokens=2000,  # Enough for most code snippets
            )

            generation_time_ms = int((time.time() - start_time) * 1000)

            # Extract generated code
            raw_code = response.choices[0].message.content

            if not raw_code:
                raise ExecutorError("OpenAI returned empty response")

            logger.debug(f"OpenAI generation completed in {generation_time_ms}ms")
            logger.debug(f"Raw code length: {len(raw_code)} chars")

            # Clean markdown blocks and explanations
            code = self._clean_code_blocks(raw_code)

            if not code:
                raise ExecutorError("Generated code is empty after cleaning")

            logger.debug(f"Cleaned code length: {len(code)} chars")

            # Validate syntax
            self._validate_syntax(code)

            logger.debug("Code syntax validated successfully")

            return code

        except Exception as e:
            if isinstance(e, (ExecutorError, CodeExecutionError)):
                raise

            logger.exception(f"OpenAI code generation failed: {e}")
            raise ExecutorError(f"Failed to generate code with OpenAI: {e}")

    async def execute(
        self,
        code: str,  # In CachedExecutor, this is the PROMPT (natural language)
        context: Dict[str, Any],
        timeout: int
    ) -> Dict[str, Any]:
        """
        Execute workflow node by generating code with AI and running in E2B.

        This method treats 'code' parameter as a natural language PROMPT,
        not hardcoded Python code.

        Flow:
        1. Build complete prompt with KnowledgeManager (task + context + integration docs)
        2. Generate Python code with OpenAI (retry up to 3 times)
        3. Execute generated code in E2B sandbox
        4. If execution fails, retry with error feedback
        5. Return result with AI metadata

        Args:
            code: Natural language prompt/task description (NOT Python code)
            context: Current workflow context
            timeout: Execution timeout in seconds (for E2B)

        Returns:
            Updated context with AI metadata:
            {
                ...context updates from execution...,
                "_ai_metadata": {
                    "model": "gpt-4o-mini",
                    "prompt": "Extract total from invoice",
                    "generated_code": "import fitz\n...",
                    "code_length": 450,
                    "tokens_input": 7000,
                    "tokens_output": 750,
                    "cost_usd": 0.0015,
                    "generation_time_ms": 1800,
                    "execution_time_ms": 1200,
                    "attempts": 1,
                    "cache_hit": False  # Phase 2
                }
            }

        Raises:
            ExecutorError: If generation fails after 3 attempts
            E2BExecutionError: If execution fails after 3 attempts
        """
        import time

        prompt_task = code  # 'code' parameter is actually the prompt
        error_history = []
        generated_code = None
        total_start_time = time.time()

        logger.info(f"CachedExecutor executing task: {prompt_task[:100]}...")

        # Retry loop (max 3 attempts)
        for attempt in range(1, 4):
            try:
                logger.info(f"Attempt {attempt}/3: Generating code...")

                # 1. Build complete prompt with knowledge
                full_prompt = self.knowledge_manager.build_prompt(
                    task=prompt_task,
                    context=context,
                    error_history=error_history if error_history else None
                )

                logger.debug(f"Full prompt length: {len(full_prompt)} chars (~{len(full_prompt)//4} tokens)")

                # 2. Generate code with OpenAI
                generation_start = time.time()
                generated_code = await self._generate_code(full_prompt)
                generation_time_ms = int((time.time() - generation_start) * 1000)

                logger.info(f"Code generated successfully in {generation_time_ms}ms")
                logger.debug(f"Generated code:\n{generated_code}")

                # 3. Execute code with E2B
                execution_start = time.time()
                result = await self.e2b_executor.execute(
                    code=generated_code,
                    context=context,
                    timeout=timeout
                )
                execution_time_ms = int((time.time() - execution_start) * 1000)

                # 3.5. Validate that result is JSON-serializable
                # This prevents storing complex objects (email.Message, file handles, etc.)
                # If validation fails, we'll retry with error feedback to the AI
                is_serializable, serialization_error = is_json_serializable(result)

                if not is_serializable:
                    # Get detailed stats about what's wrong
                    stats = get_context_stats(result)
                    problematic_keys = [
                        f"{item['key']} ({item['type']})"
                        for item in stats.get('problematic_details', [])
                    ]

                    error_message = (
                        f"Generated code produced non-JSON-serializable output: {serialization_error}\n"
                        f"Problematic keys: {', '.join(problematic_keys)}\n\n"
                        f"Remember: Context must only contain JSON-serializable types:\n"
                        f"  ✅ Allowed: str, int, float, bool, None, list, dict\n"
                        f"  ❌ Not allowed: email.Message, file handles, custom objects\n\n"
                        f"Example FIX:\n"
                        f"  ❌ context['email_obj'] = msg  # msg is email.Message\n"
                        f"  ✅ context['email_from'] = msg.get('From')  # Extract string instead"
                    )

                    logger.warning(
                        f"❌ Serialization validation failed on attempt {attempt}/3: "
                        f"{', '.join(problematic_keys)}"
                    )

                    # Raise as CodeExecutionError to trigger retry
                    raise CodeExecutionError(
                        message=error_message,
                        code=generated_code,
                        error_details=f"Problematic keys: {', '.join(problematic_keys)}"
                    )

                # 4. Success! Add AI metadata
                total_time_ms = int((time.time() - total_start_time) * 1000)

                token_info = self._estimate_tokens(full_prompt, generated_code)

                result["_ai_metadata"] = {
                    "model": "gpt-4o-mini",
                    "prompt": prompt_task,
                    "generated_code": generated_code,
                    "code_length": len(generated_code),
                    "tokens_input": token_info["tokens_input"],
                    "tokens_output": token_info["tokens_output"],
                    "tokens_total": token_info["tokens_total"],
                    "cost_usd": token_info["cost_usd"],
                    "generation_time_ms": generation_time_ms,
                    "execution_time_ms": execution_time_ms,
                    "total_time_ms": total_time_ms,
                    "attempts": attempt,
                    "cache_hit": False  # Phase 1 MVP - no cache yet
                }

                logger.info(
                    f"✅ CachedExecutor success on attempt {attempt}/3 "
                    f"(generation: {generation_time_ms}ms, execution: {execution_time_ms}ms, "
                    f"cost: ${token_info['cost_usd']:.6f})"
                )

                return result

            except (CodeExecutionError, E2BSandboxError, E2BTimeoutError) as e:
                # Execution failed - add to error history for next retry
                logger.warning(
                    f"Attempt {attempt}/3 failed: {e.__class__.__name__}: {str(e)[:200]}"
                )

                error_history.append({
                    "attempt": attempt,
                    "error": str(e),
                    "code": generated_code if generated_code else ""
                })

                # If this was the last attempt, raise
                if attempt == 3:
                    logger.error(
                        f"❌ CachedExecutor failed after 3 attempts. "
                        f"Last error: {e.__class__.__name__}: {str(e)[:200]}"
                    )
                    raise ExecutorError(
                        f"Failed to generate and execute code after 3 attempts. "
                        f"Last error: {e}"
                    )

                # Otherwise, retry with error feedback
                logger.info(f"Retrying with error feedback...")

            except Exception as e:
                # Unexpected error - fail immediately
                logger.exception(f"Unexpected error in CachedExecutor: {e}")
                raise ExecutorError(f"CachedExecutor unexpected error: {e}")

        # Should never reach here (loop always returns or raises)
        raise ExecutorError("CachedExecutor failed unexpectedly")


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
                        if hasattr(execution, 'logs') and execution.logs:
                            logger.error(f"Full stdout: {execution.logs.stdout}")

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
                        updated_context = output_json.get("context_updates", {})

                        # Log status and message if present
                        status = output_json.get("status")
                        message = output_json.get("message")
                        if status:
                            logger.debug(f"Execution status: {status}")
                        if message:
                            logger.debug(f"Execution message: {message}")

                        # If status is "error", log it but still return context_updates
                        if status == "error":
                            logger.warning(f"Code reported error status: {message}")
                    else:
                        # Legacy format or direct context update
                        updated_context = output_json

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
