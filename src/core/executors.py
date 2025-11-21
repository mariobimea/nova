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
from .cache_manager import CodeCacheManager
from .cache_utils import generate_cache_key

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
        Initialize CachedExecutor with Multi-Agent Architecture + Code Cache.

        Args:
            db_session: Optional SQLAlchemy session for code cache.
                       If provided, enables caching of AI-generated code.
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

        # Store db_session
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

        # Store E2B executor for cache hits (direct code execution)
        self.e2b = e2b_executor

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

        # Initialize Code Cache Manager
        self.cache_manager = CodeCacheManager(db_session) if db_session else None

        cache_status = "enabled" if self.cache_manager else "disabled (no DB session)"
        logger.info(f"CachedExecutor initialized with Multi-Agent Architecture (model: {default_model}, cache: {cache_status})")

    async def execute(
        self,
        code: str,  # In CachedExecutor, this is the PROMPT (natural language)
        context: Dict[str, Any],
        timeout: int,
        workflow: Optional[Dict[str, Any]] = None,
        node: Optional[Dict[str, Any]] = None,
        context_manager: Optional[Any] = None  # 🔥 NUEVO: Recibir ContextManager
    ) -> tuple[Dict[str, Any], Optional[Any]]:
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
            context_manager: Optional ContextManager to maintain analysis history between nodes

        Returns:
            Tuple of (updated_context, context_manager):
            - updated_context: Dict with context updates and AI metadata:
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
            - context_manager: Updated ContextManager with new analysis history

        Raises:
            ExecutorError: If execution fails after max retries
        """
        prompt_task = code  # 'code' parameter is actually the prompt

        logger.info(f"🚀 CachedExecutor executing with Multi-Agent Architecture")
        logger.info(f"   Task: {prompt_task[:100]}...")
        logger.info(f"   Context keys: {list(context.keys())}")
        logger.info(f"   Timeout: {timeout}s")

        # 🔥 NUEVO: Crear ContextManager si no se proporciona
        if context_manager is None:
            from .context import ContextManager
            context_manager = ContextManager(context)
            logger.info(f"   Created new ContextManager")
        else:
            logger.info(f"   Using provided ContextManager with {len(context_manager.get_summary().analysis_history)} previous analyses")

        # Extract node_type, node_id, workflow_id
        node_type = None
        node_id = None
        workflow_id = None

        if node and isinstance(node, dict):
            node_type = node.get("type")
            node_id = node.get("id")
            logger.info(f"   Node type: {node_type}")
            logger.info(f"   Node ID: {node_id}")

        if workflow and isinstance(workflow, dict):
            workflow_id = workflow.get("id")

        # ═══════════════════════════════════════════════════════
        # 🔑 CALCULAR CACHE KEY AL INICIO (antes de cualquier modificación)
        # ═══════════════════════════════════════════════════════
        cache_key_inicial = None
        if self.cache_manager:
            cache_key_inicial = generate_cache_key(prompt_task, context)
            logger.info(f"🔑 Cache key inicial: {cache_key_inicial[:16]}...")

        # ═══════════════════════════════════════════════════════
        # CACHE LOOKUP (if cache enabled)
        # ═══════════════════════════════════════════════════════
        if self.cache_manager and cache_key_inicial:
            try:
                cached_entry = await self.cache_manager.lookup_by_key(cache_key_inicial)

                if cached_entry:
                    # ✅ CACHE HIT - Execute cached code directly
                    logger.info(f"🎯 Cache HIT! Executing cached code (reused {cached_entry.times_reused} times)")

                    try:
                        # Execute cached code with E2B
                        import time
                        start_time = time.time()

                        result = await self.e2b.execute_code(
                            code=cached_entry.generated_code,
                            context=context,
                            timeout=timeout
                        )

                        execution_time_ms = (time.time() - start_time) * 1000

                        # Record success
                        await self.cache_manager.record_success(
                            cache_key=cached_entry.cache_key,
                            execution_time_ms=execution_time_ms
                        )

                        # Add cache metadata to _ai_metadata (so it gets saved to DB)
                        if '_ai_metadata' not in result:
                            result['_ai_metadata'] = {}
                        result['_ai_metadata']['_cache_metadata'] = {
                            'cache_hit': True,
                            'cache_key': cached_entry.cache_key[:16] + "...",
                            'times_reused': cached_entry.times_reused + 1,
                            'original_cost_usd': float(cached_entry.cost_usd) if cached_entry.cost_usd else 0.0,
                            'cost_saved_usd': float(cached_entry.cost_usd) if cached_entry.cost_usd else 0.0
                        }

                        logger.info(f"✅ Cached code executed successfully (saved ${cached_entry.cost_usd:.4f})")
                        return result, context_manager  # 🔥 NUEVO: Retornar tupla

                    except Exception as e:
                        # Cached code failed - fallback to AI generation
                        logger.warning(f"⚠️  Cached code failed: {e}")
                        await self.cache_manager.record_failure(
                            cache_key=cached_entry.cache_key,
                            error_message=str(e)
                        )

                        # Check if we should invalidate this cache entry
                        if cached_entry.success_rate < 0.7 and cached_entry.times_reused >= 3:
                            logger.error(f"🗑️  Cache entry unreliable, deleting: {cached_entry.cache_key[:16]}...")
                            await self.cache_manager.delete(cached_entry.cache_key)

                        logger.info(f"🔄 Falling back to AI generation")
                        # Continue to AI generation below

            except Exception as e:
                logger.warning(f"Cache lookup failed: {e}. Continuing with AI generation.")

        # ═══════════════════════════════════════════════════════
        # CACHE MISS or NO CACHE - Generate with AI
        # ═══════════════════════════════════════════════════════
        try:
            # 🔥 NUEVO: Pasar context_manager al orchestrator
            result, updated_context_manager = await self.orchestrator.execute_workflow(
                task=prompt_task,
                context=context,
                timeout=timeout,
                node_type=node_type,
                node_id=node_id,
                context_manager=context_manager  # 🔥 NUEVO: Pasar context_manager
            )

            # ═══════════════════════════════════════════════════════
            # SAVE TO CACHE (if enabled and execution successful)
            # ═══════════════════════════════════════════════════════
            ai_metadata = result.get('_ai_metadata', {})
            execution_failed = ai_metadata.get('status') == 'failed' or ai_metadata.get('final_error')

            if self.cache_manager and cache_key_inicial and not execution_failed:
                try:
                    # Extract metadata from orchestrator result
                    code_gen_meta = ai_metadata.get('code_generation', {})

                    # CodeGenerator returns {"code": "...", "model": "...", ...}
                    generated_code = code_gen_meta.get('code', '')
                    model = code_gen_meta.get('model', 'gpt-4o-mini')

                    # Calculate tokens and cost from timings metadata if available
                    # TODO: CodeGenerator should return tokens_used and cost_usd
                    tokens_used = 0  # Will be updated when CodeGenerator returns this
                    cost_usd = 0.0   # Will be updated when CodeGenerator returns this

                    if generated_code:
                        # Add generated_code to ai_metadata for engine to use in Chain of Work
                        ai_metadata['generated_code'] = generated_code

                        # 🔑 GUARDAR con el MISMO cache_key_inicial (calculado al inicio)
                        await self.cache_manager.save_with_key(
                            cache_key=cache_key_inicial,
                            generated_code=generated_code,
                            model=model,
                            original_prompt=prompt_task,
                            tokens_used=tokens_used,
                            cost_usd=cost_usd,
                            workflow_id=workflow_id,
                            node_id=node_id
                        )

                        # Add cache metadata to _ai_metadata (so it gets saved to DB)
                        if '_ai_metadata' not in result:
                            result['_ai_metadata'] = {}
                        result['_ai_metadata']['_cache_metadata'] = {
                            'cache_hit': False,
                            'cache_key': cache_key_inicial[:16] + "...",
                            'saved_for_future': True
                        }

                        # Also add to ai_metadata variable for consistency
                        ai_metadata['_cache_metadata'] = result['_ai_metadata']['_cache_metadata']

                        logger.info(f"💾 Code saved to cache for future reuse (code length: {len(generated_code)} chars)")
                    else:
                        logger.warning(f"⚠️  No generated code found in code_generation metadata, skipping cache save")
                        logger.warning(f"   code_generation keys: {list(code_gen_meta.keys())}")

                except Exception as e:
                    logger.error(f"❌ Failed to save to cache: {e}")
                    import traceback
                    logger.error(traceback.format_exc())

            elif self.cache_manager and execution_failed:
                logger.info(f"🚫 Not caching (execution failed)")

            logger.info(f"✅ Multi-Agent execution completed successfully")
            return result, updated_context_manager  # 🔥 NUEVO: Retornar tupla

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
        Inject context into code using base64 encoding for safety.

        Args:
            code: Original Python code
            context: Context to inject

        Returns:
            Code with context injection

        Uses base64 encoding to safely pass context with ANY characters
        (including newlines, quotes, backslashes, nested JSON, etc.)
        This is more robust than manual escaping.
        """
        import base64

        # Serialize context to JSON
        context_json = json.dumps(context, default=str)

        # Encode to base64 to avoid any escaping issues
        context_b64 = base64.b64encode(context_json.encode('utf-8')).decode('ascii')

        # Check if code already has a print statement
        # AI-generated code (from CachedExecutor) already includes print(json.dumps(...))
        # So we should NOT add another print statement
        has_print = 'print(' in code and 'json.dumps' in code

        if has_print:
            # Code already prints output - just inject context
            full_code = f"""import json
import base64

# Decode context from base64 (safe for ANY characters)
_context_b64 = "{context_b64}"
_context_json = base64.b64decode(_context_b64).decode('utf-8')
context = json.loads(_context_json)

# User code (already includes output print)
{code}
"""
        else:
            # Code doesn't print - add print statement for E2B
            full_code = f"""import json
import base64

# Decode context from base64 (safe for ANY characters)
_context_b64 = "{context_b64}"
_context_json = base64.b64decode(_context_b64).decode('utf-8')
context = json.loads(_context_json)

# User code
{code}

# Output updated context (use ensure_ascii for E2B stdout compatibility)
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
