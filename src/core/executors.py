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
        Initialize CachedExecutor.

        Args:
            db_session: Optional SQLAlchemy session for cache lookups (Phase 2).
                       Currently unused in Phase 1 (no cache implementation yet).
            default_model: Default model to use if not specified in workflow/node.
                          Defaults to "gpt-4o-mini" (cheapest OpenAI model).

        Requires OPENAI_API_KEY environment variable.
        """
        import os
        from .ai.knowledge_manager import KnowledgeManager
        from .model_registry import ModelRegistry

        # Store db_session for future cache implementation (Phase 2)
        self.db_session = db_session

        # Store default model
        self.default_model = default_model

        # Validate that default model exists
        if not ModelRegistry.is_valid_model(default_model):
            available = ModelRegistry.list_models()
            raise ValueError(
                f"Invalid default_model: '{default_model}'. "
                f"Available models: {', '.join(available)}"
            )

        # Initialize E2B executor (for code execution)
        # Use custom template if E2B_TEMPLATE_ID is set
        template_id = os.getenv("E2B_TEMPLATE_ID")
        self.e2b_executor = E2BExecutor(template=template_id)

        # Initialize Knowledge Manager (for prompt building)
        self.knowledge_manager = KnowledgeManager()

        logger.info(f"CachedExecutor initialized with default model: {default_model}")

    def _resolve_model(
        self,
        node: Optional[Dict[str, Any]],
        workflow: Optional[Dict[str, Any]]
    ) -> str:
        """
        Resolve which model to use for code generation.

        Priority (highest to lowest):
        1. Node-level model specification (node.get("model"))
        2. Workflow-level model specification (workflow.get("model"))
        3. Default model from __init__

        Args:
            node: Optional node dictionary (may contain "model" field)
            workflow: Optional workflow dictionary (may contain "model" field)

        Returns:
            Model name to use

        Example:
            >>> executor = CachedExecutor(default_model="gpt-4o-mini")
            >>> executor._resolve_model(
            ...     node={"model": "gpt-5-codex"},
            ...     workflow={"model": "gpt-5-mini"}
            ... )
            "gpt-5-codex"  # Node overrides workflow
        """
        # Priority 1: Node-level model
        if node and node.get("model"):
            return node["model"]

        # Priority 2: Workflow-level model
        if workflow and workflow.get("model"):
            return workflow["model"]

        # Priority 3: Default model
        return self.default_model

    # NOTE: Methods _clean_code_blocks(), _validate_syntax(), and _estimate_tokens()
    # removed - now implemented in OpenAIProvider for better separation of concerns
    # This keeps CachedExecutor clean and provider-agnostic

    def _format_error_history(self, error_history: Optional[List[Dict]]) -> str:
        """Format error history for tool calling prompt."""
        if not error_history:
            return ""

        lines = []
        for i, attempt in enumerate(error_history, 1):
            error = attempt.get("error", "Unknown error")
            code = attempt.get("code", "")

            lines.append(f"Attempt {i}: FAILED")
            lines.append(f"Error: {error[:300]}")  # Truncate long errors
            if code:
                lines.append(f"Code preview: {code[:200]}...")
            lines.append("")

        return "\n".join(lines)

    def _extract_full_documentation(self, tool_calls: List[Dict]) -> str:
        """
        Extract full documentation content from tool call results.

        This reconstructs what documentation the AI actually had access to
        when generating code. Useful for debugging why AI made certain choices.

        Args:
            tool_calls: List of tool call dicts with 'result_preview' field

        Returns:
            Concatenated documentation content
        """
        if not tool_calls:
            return ""

        docs_parts = []
        for i, tc in enumerate(tool_calls, 1):
            query = tc.get("arguments", {}).get("query", "unknown")
            source = tc.get("arguments", {}).get("source", "all")

            docs_parts.append(f"\n=== Search {i}: '{query}' (source: {source}) ===\n")

            # result_preview contains the full documentation the AI received
            result = tc.get("result_preview", "")
            if result:
                docs_parts.append(result)
            else:
                docs_parts.append("[No results found]\n")

        return "".join(docs_parts)

    async def execute(
        self,
        code: str,  # In CachedExecutor, this is the PROMPT (natural language)
        context: Dict[str, Any],
        timeout: int,
        workflow: Optional[Dict[str, Any]] = None,
        node: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute workflow node by generating code with AI and running in E2B.

        This method treats 'code' parameter as a natural language PROMPT,
        not hardcoded Python code.

        Flow:
        1. Resolve which model to use (node > workflow > default)
        2. Get model provider from registry
        3. Generate Python code with provider (retry up to 3 times)
        4. Execute generated code in E2B sandbox
        5. If execution fails, retry with error feedback
        6. Return result with AI metadata

        Args:
            code: Natural language prompt/task description (NOT Python code)
            context: Current workflow context
            timeout: Execution timeout in seconds (for E2B)
            workflow: Optional workflow dictionary (for model resolution)
            node: Optional node dictionary (for model resolution)

        Returns:
            Updated context with AI metadata:
            {
                ...context updates from execution...,
                "_ai_metadata": {
                    "model": "gpt-5-mini",
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
        from .model_registry import ModelRegistry

        prompt_task = code  # 'code' parameter is actually the prompt
        error_history = []
        generated_code = None
        total_start_time = time.time()

        # ═══════════════════════════════════════════════════════════════
        # MODEL RESOLUTION: Determine which model to use
        # ═══════════════════════════════════════════════════════════════

        model_name = self._resolve_model(node, workflow)
        logger.info(f"Resolved model: {model_name}")

        # Get provider from registry
        try:
            provider = ModelRegistry.get_provider(model_name)
            logger.info(f"Using provider: {provider.__class__.__name__}")
        except ValueError as e:
            raise ExecutorError(f"Failed to get model provider: {e}")

        logger.info(f"CachedExecutor executing task: {prompt_task[:100]}...")

        # ═══════════════════════════════════════════════════════════════
        # AI SELF-DETERMINATION: AI decides if analysis needed
        # ═══════════════════════════════════════════════════════════════

        enriched_context = context.copy()
        analysis_metadata = None
        max_stages = 2  # analysis + task
        current_stage = 0

        # Retry loop (max 3 attempts) - applies to FINAL task execution
        for attempt in range(1, 4):
            try:
                logger.info(f"Attempt {attempt}/3: Generating code...")

                # DEBUG: Log context being passed to AI
                logger.info(f"📊 Context passed to AI (attempt {attempt}):")
                for key, value in enriched_context.items():
                    if isinstance(value, str) and len(value) > 100:
                        logger.info(f"   {key}: <string, {len(value)} chars>")
                    elif isinstance(value, bytes):
                        logger.info(f"   {key}: <bytes, {len(value)} bytes>")
                    else:
                        logger.info(f"   {key}: {value}")

                # ═══════════════════════════════════════════════════════════
                # STAGE LOOP: AI decides if analysis needed (max 2 stages)
                # ═══════════════════════════════════════════════════════════

                for stage_num in range(1, max_stages + 1):
                    logger.info(f"🔄 Stage {stage_num}/{max_stages}")

                    # 1. Generate code with OpenAI tool calling
                    # AI decides: analysis or task?
                    generation_start = time.time()

                    # Build context summary
                    context_summary = self.knowledge_manager.create_context_summary(
                        enriched_context
                    )

                    # Build prompt with self-determination instructions
                    system_prompt = self._build_self_determination_prompt(
                        task=prompt_task,
                        context_summary=context_summary,
                        is_first_stage=(stage_num == 1 and attempt == 1)
                    )

                    generated_code, tool_metadata = await provider.generate_code_with_tools(
                        task=prompt_task,
                        context=enriched_context,
                        error_history=error_history if error_history else None,
                        system_message=system_prompt,  # Override with self-determination prompt
                        knowledge_manager=self.knowledge_manager
                    )
                    generation_time_ms = int((time.time() - generation_start) * 1000)

                    logger.info(f"Code generated successfully in {generation_time_ms}ms")
                    logger.info(f"Generated code ({len(generated_code)} chars):\n{generated_code}")

                    # Log tool calling details
                    if tool_metadata.get("tool_calls"):
                        logger.info(f"🔍 AI made {tool_metadata['total_tool_calls']} documentation searches:")
                        for i, tc in enumerate(tool_metadata["tool_calls"], 1):
                            logger.info(f"   {i}. {tc['function']}({tc['arguments']})")

                    # 2. Detect which stage AI chose
                    detected_stage = self._detect_stage_from_code(generated_code)
                    logger.info(f"🔍 Detected stage: {detected_stage.upper()}")

                    if detected_stage == "analysis":
                        # ═══ STAGE 1: AI decided to analyze data first ═══
                        logger.info("📊 AI decided to analyze data first")

                        try:
                            # Execute analysis code
                            execution_start = time.time()
                            analysis_result = await self.e2b_executor.execute(
                                code=generated_code,
                                context=enriched_context,
                                timeout=min(timeout // 2, 30)  # Half timeout or 30s max
                            )
                            execution_time_ms = int((time.time() - execution_start) * 1000)

                            # Enrich context with analysis results
                            enriched_context['_data_analysis'] = analysis_result

                            # Track analysis metadata
                            analysis_metadata = {
                                "analysis_code": generated_code,
                                "analysis_result": analysis_result,
                                "generation_time_ms": generation_time_ms,
                                "execution_time_ms": execution_time_ms,
                                "total_time_ms": generation_time_ms + execution_time_ms,
                                "tool_calls": tool_metadata.get("tool_calls", [])
                            }

                            logger.info(
                                f"✅ Analysis complete: "
                                f"{list(analysis_result.keys()) if isinstance(analysis_result, dict) else type(analysis_result)}"
                            )

                            # Continue to next stage (task generation)
                            continue

                        except Exception as e:
                            logger.warning(f"⚠️ Analysis stage failed: {e}")
                            # Add error to context and continue
                            enriched_context['_data_analysis'] = {
                                "error": str(e),
                                "note": "Analysis failed, proceeding without analysis"
                            }
                            # Continue to task stage
                            continue

                    # ═══ STAGE 2 (or direct): Execute task code ═══
                    elif detected_stage == "task":
                        logger.info("⚙️ AI generated task code")
                        # Break out of stage loop, proceed to execution
                        break

                # At this point, generated_code is the TASK code
                # (either direct, or after analysis enrichment)

                # 3. Execute task code with E2B
                execution_start = time.time()
                result = await self.e2b_executor.execute(
                    code=generated_code,
                    context=enriched_context,  # ← Use enriched context
                    timeout=timeout
                )
                execution_time_ms = int((time.time() - execution_start) * 1000)

                # 3.5. AI validates output (semantic correctness)
                # This replaces hardcoded validation rules with AI understanding
                logger.info("🤖 AI validating execution output...")
                ai_validation = await self._validate_output_with_ai(
                    task=prompt_task,
                    context_before=enriched_context,
                    context_after=result,
                    generated_code=generated_code,
                    node_type=node.get("type", "ActionNode") if node else "ActionNode",
                    model_name=model_name
                )

                if not ai_validation.get("valid", True):
                    # AI detected invalid output - retry with feedback
                    validation_reason = ai_validation.get("reason", "AI validation failed")
                    logger.warning(
                        f"❌ AI validation failed on attempt {attempt}/3: {validation_reason}"
                    )

                    # Raise as CodeExecutionError to trigger retry with feedback
                    raise CodeExecutionError(
                        message=f"AI Validation Failed: {validation_reason}",
                        code=generated_code,
                        error_details=validation_reason
                    )

                logger.info("✅ AI validation passed")

                # 3.6. Serialization check (KEEP - safety validation)
                # This prevents storing complex objects (email.Message, file handles, etc.)
                # If validation fails, we'll retry with error feedback to the AI
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

                # Estimate tokens using provider's method
                estimated_tokens_input = provider.estimate_tokens(prompt_task + str(context))
                estimated_tokens_output = provider.estimate_tokens(generated_code)

                # Calculate cost using provider's pricing
                estimated_cost = provider.estimate_cost(estimated_tokens_input, estimated_tokens_output)

                # Extract full documentation that AI received
                documentation_retrieved = self._extract_full_documentation(
                    tool_metadata.get("tool_calls", [])
                )

                result["_ai_metadata"] = {
                    # Model & generation
                    "model": model_name,  # Use resolved model name
                    "prompt_task": prompt_task,  # Short task description
                    "generated_code": generated_code,
                    "code_length": len(generated_code),

                    # Costs & timing (estimated for tool calling mode)
                    "tokens_input_estimated": estimated_tokens_input,
                    "tokens_output_estimated": estimated_tokens_output,
                    "cost_usd_estimated": round(estimated_cost, 6),
                    "generation_time_ms": generation_time_ms,
                    "execution_time_ms": execution_time_ms,
                    "total_time_ms": total_time_ms,
                    "attempts": attempt,
                    "cache_hit": False,  # Phase 1 MVP - no cache yet

                    # Tool calling metadata (for debugging)
                    "tool_calling_enabled": True,
                    "retrieval_method": "dynamic_tool_calling",  # AI searches docs on demand
                    "tool_calls": tool_metadata.get("tool_calls", []),  # All documentation searches
                    "tool_iterations": tool_metadata.get("tool_iterations", 0),  # Number of AI iterations
                    "total_tool_calls": tool_metadata.get("total_tool_calls", 0),  # Total searches made
                    "context_summary": tool_metadata.get("context_summary", ""),  # What context AI saw
                    "documentation_retrieved": documentation_retrieved,  # Full docs AI had access to

                    # ⭐ Two-stage generation metadata (AI self-determination)
                    "two_stage_enabled": analysis_metadata is not None,
                    "ai_self_determined": True,  # AI decided if analysis needed
                    "stages_used": 2 if analysis_metadata else 1,  # 1=direct task, 2=analysis+task
                    "analysis_metadata": analysis_metadata,  # Stage 1 details (if ran)
                }

                logger.info(
                    f"✅ CachedExecutor success on attempt {attempt}/3 "
                    f"(generation: {generation_time_ms}ms, execution: {execution_time_ms}ms, "
                    f"est_cost: ${estimated_cost:.6f})"
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

                # If this was the last attempt, raise with full metadata
                if attempt == 3:
                    logger.error(
                        f"❌ CachedExecutor failed after 3 attempts. "
                        f"Last error: {e.__class__.__name__}: {str(e)[:200]}"
                    )
                    logger.info(
                        f"📝 Preserving generated code ({len(generated_code) if generated_code else 0} chars) "
                        f"and {len(error_history)} attempts for debugging"
                    )

                    # Include generated code and ALL attempts for full traceability
                    raise ExecutorError(
                        message=f"Failed to generate and execute code after 3 attempts. Last error: {e}",
                        generated_code=generated_code,  # Last generated code
                        error_history=error_history      # All 3 attempts with errors
                    )

                # Otherwise, retry with error feedback
                logger.info(f"Retrying with error feedback...")

            except Exception as e:
                # Unexpected error - fail immediately
                logger.exception(f"Unexpected error in CachedExecutor: {e}")
                # Include partial error history if available
                raise ExecutorError(
                    message=f"CachedExecutor unexpected error: {e}",
                    generated_code=generated_code if 'generated_code' in locals() else None,
                    error_history=error_history if 'error_history' in locals() else []
                )

        # Should never reach here (loop always returns or raises)
        raise ExecutorError(
            message="CachedExecutor failed unexpectedly",
            generated_code=None,
            error_history=[]
        )

    # ═══════════════════════════════════════════════════════════════════════
    # AI SELF-DETERMINATION: Two-Stage Code Generation
    # ═══════════════════════════════════════════════════════════════════════

    def _detect_stage_from_code(self, code: str) -> str:
        """
        Detect which stage the AI generated code for.

        The AI marks its code with stage identifiers:
        - "# STAGE: ANALYSIS" → Stage 1 (data analysis)
        - "# STAGE: TASK" → Stage 2 (task execution)

        Args:
            code: Generated Python code

        Returns:
            "analysis" or "task"
        """
        # Look for stage marker in first 10 lines
        lines = code.strip().split('\n')[:10]

        for line in lines:
            line_clean = line.strip().upper()
            if "# STAGE: ANALYSIS" in line_clean:
                return "analysis"
            elif "# STAGE: TASK" in line_clean:
                return "task"

        # Default: assume task if no marker
        logger.warning("⚠️ No stage marker found in code, assuming TASK stage")
        return "task"

    async def _execute_with_ai_self_determination(
        self,
        task: str,
        context: Dict[str, Any],
        timeout: int
    ) -> Dict[str, Any]:
        """
        Execute using AI self-determination approach.

        Flow:
        1. AI receives task + context
        2. AI decides: Need analysis? Or go straight to task?
        3. AI generates code marked with stage identifier
        4. System detects stage and routes accordingly
        5. If analysis stage: execute, enrich context, loop back to step 1
        6. If task stage: execute and return results

        This is more flexible than heuristics because AI makes the decision
        based on the actual task requirements, not hardcoded rules.

        Args:
            task: User's task description
            context: Execution context (may contain large data)
            timeout: Execution timeout in seconds

        Returns:
            Execution result with metadata

        Raises:
            ExecutorError: If execution fails
        """
        import time

        logger.info("🤖 Using AI SELF-DETERMINATION approach")

        enriched_context = context.copy()
        analysis_metadata = None
        max_stages = 2  # Prevent infinite loops (analysis + task)

        for stage_num in range(1, max_stages + 1):
            logger.info(f"═══ STAGE {stage_num}/{max_stages} ═══")

            # Build context summary for this stage
            context_summary = self.knowledge_manager.create_context_summary(
                enriched_context
            )

            # Build prompt with self-determination instructions
            system_prompt = self._build_self_determination_prompt(
                task=task,
                context_summary=context_summary,
                is_first_stage=(stage_num == 1)
            )

            # Generate code with tool calling (docs search available)
            generation_start = time.time()
            result = await self._generate_code_with_tools(
                context=enriched_context,
                system_message=system_prompt
            )
            generation_time_ms = int((time.time() - generation_start) * 1000)

            generated_code = result['code']
            tool_calls = result.get('tool_calls', [])

            # Detect which stage AI chose
            detected_stage = self._detect_stage_from_code(generated_code)
            logger.info(f"🔍 Detected stage: {detected_stage.upper()}")

            if detected_stage == "analysis":
                # AI chose to analyze data first
                logger.info("📊 AI decided to analyze data first")

                try:
                    # Execute analysis code
                    execution_start = time.time()
                    analysis_result = await self.sandbox.execute_code(
                        code=generated_code,
                        context=enriched_context,
                        timeout=timeout
                    )
                    execution_time_ms = int((time.time() - execution_start) * 1000)

                    # Enrich context with analysis results
                    enriched_context['_data_analysis'] = analysis_result

                    # Track analysis metadata
                    analysis_metadata = {
                        "analysis_code": generated_code,
                        "analysis_result": analysis_result,
                        "generation_time_ms": generation_time_ms,
                        "execution_time_ms": execution_time_ms,
                        "total_time_ms": generation_time_ms + execution_time_ms,
                        "tool_calls": tool_calls
                    }

                    logger.info(
                        f"✅ Analysis complete: "
                        f"{list(analysis_result.keys()) if isinstance(analysis_result, dict) else type(analysis_result)}"
                    )

                    # Continue to next stage (task generation)
                    continue

                except Exception as e:
                    logger.warning(f"⚠️ Analysis stage failed: {e}")
                    # Add error to context and continue
                    enriched_context['_data_analysis'] = {
                        "error": str(e),
                        "note": "Analysis failed, proceeding without analysis"
                    }
                    continue

            elif detected_stage == "task":
                # AI chose to go straight to task (or this is stage 2 after analysis)
                logger.info("⚙️ AI generating task code")

                # Execute task code
                execution_start = time.time()
                task_result = await self.sandbox.execute_code(
                    code=generated_code,
                    context=enriched_context,
                    timeout=timeout
                )
                execution_time_ms = int((time.time() - execution_start) * 1000)

                # Build final metadata
                metadata = {
                    "_ai_metadata": {
                        "two_stage_enabled": True,
                        "ai_self_determined": True,
                        "stages_used": stage_num,
                        "analysis_metadata": analysis_metadata,
                        "task_metadata": {
                            "task_code": generated_code,
                            "generation_time_ms": generation_time_ms,
                            "execution_time_ms": execution_time_ms,
                            "total_time_ms": generation_time_ms + execution_time_ms,
                            "tool_calls": tool_calls
                        }
                    }
                }

                # Merge task result with metadata
                if isinstance(task_result, dict):
                    return {**task_result, **metadata}
                else:
                    return {"result": task_result, **metadata}

        # Should never reach here (max_stages exceeded)
        raise ExecutorError(
            message=f"Exceeded maximum stages ({max_stages})",
            generated_code=generated_code
        )

    async def _validate_output_with_ai(
        self,
        task: str,
        context_before: Dict[str, Any],
        context_after: Dict[str, Any],
        generated_code: str,
        node_type: str,
        model_name: str
    ) -> Dict[str, Any]:
        """
        Validate execution output using AI (gpt-4o-mini for speed/cost).

        The AI checks:
        1. Did the code successfully complete the task?
        2. Are outputs meaningful (not errors disguised as success)?
        3. For DecisionNode: Is there a clear boolean decision?

        Args:
            task: Original task description
            context_before: Context before execution
            context_after: Context after execution (from E2B)
            generated_code: The code that was executed
            node_type: "ActionNode" or "DecisionNode"
            model_name: Model to use for validation (usually gpt-4o-mini)

        Returns:
            {
                "valid": True/False,
                "reason": "Explanation if invalid",
                "decision_field": "field_name" (DecisionNode only),
                "decision_value": True/False (DecisionNode only)
            }
        """
        from .model_registry import ModelRegistry

        # Always use gpt-4o-mini for validation (fast + cheap)
        validator_model = "gpt-4o-mini"
        validator_provider = ModelRegistry.get_provider(validator_model)

        # Remove internal fields for cleaner validation
        context_before_clean = {k: v for k, v in context_before.items() if not k.startswith('_')}
        context_after_clean = {k: v for k, v in context_after.items() if not k.startswith('_')}

        # Build validation prompt based on node type
        if node_type == "DecisionNode":
            validation_prompt = f"""You are validating if code successfully made a boolean decision.

TASK: {task}

CONTEXT BEFORE:
{json.dumps(context_before_clean, indent=2, ensure_ascii=False)[:1500]}

CONTEXT AFTER:
{json.dumps(context_after_clean, indent=2, ensure_ascii=False)[:1500]}

VALIDATION CHECKS:
1. Is there a boolean field in the context representing the decision?
2. Common field names: 'branch_decision', 'has_X', 'is_X', 'X_found', 'should_X'
3. Did the code report any errors (check for 'error', 'exception' fields)?

Respond ONLY with valid JSON (no markdown):
{{
    "valid": true/false,
    "reason": "Brief explanation if invalid",
    "decision_field": "field_name or null",
    "decision_value": true/false/null
}}"""
        else:
            # ActionNode validation
            validation_prompt = f"""You are validating if code successfully completed a task.

TASK: {task}

CONTEXT BEFORE:
{json.dumps(context_before_clean, indent=2, ensure_ascii=False)[:1500]}

CONTEXT AFTER:
{json.dumps(context_after_clean, indent=2, ensure_ascii=False)[:1500]}

VALIDATION CHECKS:
1. Did the code add/modify fields in context?
2. Are the outputs meaningful (not empty/None)?
3. Did the code report errors (check for 'error', 'exception' fields)?
4. Does the output make sense for the task?

Respond ONLY with valid JSON (no markdown):
{{
    "valid": true/false,
    "reason": "Brief explanation if invalid"
}}"""

        try:
            # Call AI validator with low temperature for consistency
            response = await validator_provider.generate_text(
                prompt=validation_prompt,
                temperature=0.1,
                max_tokens=200
            )

            # Parse JSON response (remove markdown if present)
            response_clean = response.strip()
            if response_clean.startswith("```"):
                # Remove markdown code blocks
                lines = response_clean.split('\n')
                response_clean = '\n'.join(lines[1:-1])

            validation_result = json.loads(response_clean)

            logger.info(
                f"AI validation result: valid={validation_result.get('valid')}, "
                f"reason={validation_result.get('reason', 'N/A')}"
            )

            return validation_result

        except Exception as e:
            # If AI validation fails, default to PASS (don't block execution)
            logger.warning(f"AI validation failed: {e}. Defaulting to valid=True")
            return {"valid": True, "reason": f"AI validation error: {e}"}

    def _build_self_determination_prompt(
        self,
        task: str,
        context_summary: str,
        is_first_stage: bool
    ) -> str:
        """
        Build system prompt for AI self-determination.

        The prompt instructs the AI to:
        1. Decide if data analysis is needed
        2. Mark code with stage identifier
        3. Generate appropriate code

        Args:
            task: User's task description
            context_summary: Summarized context
            is_first_stage: Whether this is the first generation

        Returns:
            System prompt string
        """
        if is_first_stage:
            stage_instructions = """
OPTIONAL TWO-STAGE APPROACH:

If the context contains complex data (PDFs, images, large base64 strings, binary data)
that you need to UNDERSTAND before solving the task:

1. First, generate ANALYSIS code marked with:
   # STAGE: ANALYSIS

   This code should:
   - Analyze the data structure/content/format
   - Extract metadata (type, size, properties)
   - Identify key characteristics needed to solve the task
   - Return insights as a dict with clear keys

   Example:
   ```python
   # STAGE: ANALYSIS
   import base64
   import fitz  # PyMuPDF

   pdf_bytes = base64.b64decode(context['pdf_data_b64'])
   doc = fitz.open(stream=pdf_bytes, filetype="pdf")

   result = {
       "type": "pdf",
       "pages": len(doc),
       "has_text_layer": bool(doc[0].get_text().strip()),
       "file_size_kb": len(pdf_bytes) // 1024
   }
   ```

2. After analysis runs, you'll receive enriched context with results in context['_data_analysis']
3. Then generate TASK code using those insights

If the context is simple/clear (just strings, numbers, small data),
skip analysis and go directly to:

# STAGE: TASK

Your task-solving code here.
"""
        else:
            # Second stage - AI already did analysis
            stage_instructions = """
You previously analyzed the data. The analysis results are in context['_data_analysis'].

Now generate the TASK code marked with:
# STAGE: TASK

Use the analysis insights to solve the task effectively.
"""

        return f"""You are NOVA's code generation system.

Your job: Generate Python code to solve the user's task.

{stage_instructions}

AVAILABLE TOOLS:
You can call search_documentation(library, query) at ANY point to get API documentation.
Example: If you need to work with PDFs, search for "pymupdf" or "pypdf" first.

CONTEXT PROVIDED:
{context_summary}

USER TASK:
{task}

REQUIREMENTS:
- Mark your code with the appropriate stage comment
- Return results by modifying the 'context' dict
- Handle errors gracefully
- Use clear variable names

Generate the appropriate Python code now."""


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

                    # Extract context updates for successful execution
                    updated_context = output_json.get("context_updates", {})

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
