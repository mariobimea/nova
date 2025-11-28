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
from typing import Dict, Any, Optional, List, Tuple, TYPE_CHECKING
import logging

if TYPE_CHECKING:
    from .context_manager import ContextManager

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
from .rag_client import get_code_cache_client
from .schema_extractor import extract_compact_schema

logger = logging.getLogger(__name__)


class ExecutorStrategy(ABC):
    """
    Abstract interface for all execution strategies.

    All executors must implement the execute() method which:
    - Takes code, context, and optional context_manager
    - Returns tuple of (result, metadata)
    - Raises ExecutorError on failure
    """

    @abstractmethod
    async def execute(
        self,
        code: str,
        context: Dict[str, Any],
        context_manager: Optional['ContextManager'] = None,
        timeout: Optional[int] = None,
        **kwargs
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Execute code with given context.

        Args:
            code: Python code or prompt to execute
            context: Execution context (dict)
            context_manager: Optional ContextManager (CachedExecutor uses this)
            timeout: Execution timeout in seconds
            **kwargs: Additional executor-specific parameters

        Returns:
            Tuple containing:
            - result (Dict): Functional output to merge into next node's context
            - metadata (Dict): Execution metadata (cache, AI, timing, stdout/stderr)

        Side effects:
            - CachedExecutor may modify context_manager in-place

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

        # Initialize Code Cache Manager (exact hash cache)
        self.cache_manager = CodeCacheManager(db_session) if db_session else None

        # Initialize Semantic Code Cache Client (semantic similarity cache)
        try:
            self.semantic_cache = get_code_cache_client()
            logger.info("✓ Semantic Code Cache client initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize Semantic Code Cache: {e}. Semantic caching disabled.")
            self.semantic_cache = None

        cache_status = "enabled" if self.cache_manager else "disabled (no DB session)"
        semantic_cache_status = "enabled" if self.semantic_cache else "disabled"
        logger.info(f"CachedExecutor initialized with Multi-Agent Architecture")
        logger.info(f"  Model: {default_model}")
        logger.info(f"  Exact cache: {cache_status}")
        logger.info(f"  Semantic cache: {semantic_cache_status}")

    async def execute(
        self,
        code: str,  # In CachedExecutor, this is the PROMPT (natural language)
        context: Dict[str, Any],
        context_manager: Optional['ContextManager'] = None,
        timeout: Optional[int] = None,
        workflow: Optional[Dict[str, Any]] = None,
        node: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
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
            context: Current workflow context (dict)
            context_manager: Optional ContextManager to maintain analysis history between nodes
            timeout: Execution timeout in seconds (for E2B)
            workflow: Optional workflow dictionary (unused in multi-agent)
            node: Optional node dictionary (unused in multi-agent)
            **kwargs: Additional executor-specific parameters

        Returns:
            Tuple containing:
            - result (Dict): Functional output (clean, no metadata)
            - metadata (Dict): Execution metadata:
              {
                  "cache_metadata": {
                      "cache_hit": bool,
                      "cache_key": str,
                      "times_reused": int,
                      "cost_saved_usd": float
                  },
                  "ai_metadata": {
                      "input_analysis": {...},
                      "data_analysis": {...},
                      "code_generation": {...},
                      "code_validation": {...},
                      "output_validation": {...},
                      "attempts": 1-3,
                      "errors": [...],
                      "timings": {...}
                  },
                  "execution_metadata": {
                      "stdout": str,
                      "stderr": str,
                      "exit_code": int
                  }
              }

        Side effects:
            - Modifies context_manager in-place with functional result

        Raises:
            ExecutorError: If execution fails after max retries
        """
        prompt_task = code  # 'code' parameter is actually the prompt

        logger.info(f"🚀 CachedExecutor executing with Multi-Agent Architecture")
        logger.info(f"   Task: {prompt_task[:100]}...")
        logger.info(f"   Context keys: {list(context.keys())}")
        logger.info(f"   Timeout: {timeout}s")

        # Crear ContextManager si no se proporciona
        if context_manager is None:
            from .context_manager import ContextManager
            context_manager = ContextManager(initial_context=context)
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

                        # Crear metadata separado
                        metadata = {
                            'cache_metadata': {
                                'cache_hit': True,
                                'cache_key': cached_entry.cache_key[:16] + "...",
                                'times_reused': cached_entry.times_reused + 1,
                                'original_cost_usd': float(cached_entry.cost_usd) if cached_entry.cost_usd else 0.0,
                                'cost_saved_usd': float(cached_entry.cost_usd) if cached_entry.cost_usd else 0.0
                            },
                            'ai_metadata': {
                                'model': cached_entry.model,
                                'generated_code': cached_entry.generated_code,
                                'original_prompt': cached_entry.original_prompt,
                                'tokens_used': cached_entry.tokens_used or 0,
                                'cost_usd': float(cached_entry.cost_usd) if cached_entry.cost_usd else 0.0
                            },
                            'execution_metadata': {
                                'stdout': result.get('_stdout', ''),
                                'stderr': result.get('_stderr', ''),
                                'exit_code': result.get('_exit_code', 0)
                            }
                        }

                        # Limpiar result de campos internos
                        clean_result = {k: v for k, v in result.items() if not k.startswith('_')}

                        # Actualizar context_manager con resultado funcional limpio
                        context_manager.update(clean_result)

                        logger.info(f"✅ Cached code executed successfully (saved ${cached_entry.cost_usd:.4f})")
                        return clean_result, metadata

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
        # SEMANTIC CACHE LOOKUP (if enabled and cache_context provided)
        # ═══════════════════════════════════════════════════════
        cache_ctx = kwargs.get("cache_context")
        semantic_cache_metadata = None  # Will be populated if semantic cache search happens

        logger.info(f"🔎 Semantic cache check: semantic_cache={'enabled' if self.semantic_cache else 'disabled'}, cache_ctx={'present' if cache_ctx else 'missing'}")
        if self.semantic_cache and cache_ctx:
            try:
                import time
                search_start = time.time()

                semantic_query = self._build_semantic_query(prompt_task, node, cache_ctx)

                # Extract available keys from input_schema
                available_keys = list(cache_ctx.get('input_schema', {}).keys())

                # For validation, also include keys from config (credentials) and context
                # These are NOT in input_schema but ARE available in context
                all_available_keys = set(available_keys)

                # Add credential keys from config
                config_keys = cache_ctx.get('config', {})
                for key in config_keys:
                    if key.startswith('has_') and config_keys[key]:
                        # Extract actual key name (remove 'has_' prefix)
                        actual_key = key[4:]  # Remove 'has_'
                        all_available_keys.add(actual_key)

                # Add workflow config fields (always present)
                all_available_keys.update(['database_schemas', 'sender_whitelist'])

                logger.info(f"🔍 Searching semantic code cache...")
                logger.debug(f"  Schema keys: {available_keys}")
                logger.debug(f"  All available keys: {sorted(all_available_keys)}")

                # Search semantic cache with threshold 0.85
                threshold = 0.85
                top_k = 3
                matches = self.semantic_cache.search_code(
                    query=semantic_query,
                    threshold=threshold,
                    top_k=top_k,
                    available_keys=available_keys  # Still search by schema keys only
                )

                # ALSO search with threshold=0.0 to get ALL results for debugging
                all_matches = self.semantic_cache.search_code(
                    query=semantic_query,
                    threshold=0.0,  # Get ALL results regardless of score
                    top_k=10,  # Get up to 10 results for analysis
                    available_keys=available_keys
                )

                search_time_ms = (time.time() - search_start) * 1000

                # Build semantic cache search metadata
                semantic_cache_metadata = {
                    'query': semantic_query[:500] + '...' if len(semantic_query) > 500 else semantic_query,  # Truncate long queries
                    'threshold': threshold,
                    'top_k': top_k,
                    'available_keys': available_keys,
                    'all_available_keys': sorted(list(all_available_keys)),
                    'search_time_ms': round(search_time_ms, 2),
                    'results_above_threshold': [],  # Matches above 0.85
                    'all_results': []  # ALL results returned by search (for debugging)
                }

                # Add matches above threshold to metadata
                for match in matches:
                    semantic_cache_metadata['results_above_threshold'].append({
                        'score': round(match.get('score', 0), 3),
                        'node_action': match.get('node_action', 'unknown'),
                        'node_description': match.get('node_description', '')[:100],  # Truncate descriptions
                        'required_keys': match.get('metadata', {}).get('required_keys', []),
                        'libraries_used': match.get('metadata', {}).get('libraries_used', []),
                        'code': match.get('code', '')  # ✨ ADD CODE
                    })

                # Add ALL results (including below threshold) for debugging
                for match in all_matches:
                    semantic_cache_metadata['all_results'].append({
                        'score': round(match.get('score', 0), 3),
                        'node_action': match.get('node_action', 'unknown'),
                        'node_description': match.get('node_description', '')[:100],
                        'required_keys': match.get('metadata', {}).get('required_keys', []),
                        'libraries_used': match.get('metadata', {}).get('libraries_used', []),
                        'above_threshold': match.get('score', 0) >= threshold,
                        'code': match.get('code', '')  # ✨ ADD CODE
                    })

                logger.info(f"📊 Semantic cache search completed: {len(matches)} matches above {threshold}, {len(all_matches)} total results in {search_time_ms:.0f}ms")

                if matches:
                    best_match = matches[0]
                    logger.info(f"🎯 Semantic cache HIT! Score: {best_match['score']:.3f}")
                    logger.info(f"   Action: {best_match['node_action']}")
                    logger.info(f"   Description: {best_match['node_description'][:60]}...")

                    # Validate that we have all required keys for this code
                    required_keys = best_match.get('metadata', {}).get('required_keys', [])
                    can_use_cached_code = True
                    validation_reason = None

                    if required_keys:
                        required_keys_set = set(required_keys)

                        missing_keys = required_keys_set - all_available_keys
                        if missing_keys:
                            logger.warning(f"⚠️ Semantic cache match requires keys we don't have: {missing_keys}")
                            logger.warning(f"   Required: {required_keys_set}")
                            logger.warning(f"   Available: {sorted(all_available_keys)}")
                            logger.info(f"🔄 Skipping cached code, falling back to AI generation")
                            can_use_cached_code = False
                            validation_reason = f"missing_keys: {sorted(list(missing_keys))}"
                        else:
                            logger.info(f"✓ All required keys available: {required_keys_set}")
                            validation_reason = "all_keys_available"

                    if can_use_cached_code:
                        try:
                            # Execute semantic cached code
                            import time
                            start_time = time.time()

                            result = await self.e2b.execute_code(
                                code=best_match['code'],
                                context=context,
                                timeout=timeout
                            )

                            execution_time_ms = (time.time() - start_time) * 1000

                            # Validate output
                            from .output_validator import auto_validate_output

                            # Get task description
                            task = node.get('description', prompt_task) if node else prompt_task

                            # Validate using auto_validate_output
                            validation_result = auto_validate_output(
                                task=task,
                                context_before=context,
                                context_after=result,
                                generated_code=best_match['code']
                            )

                            if validation_result.valid:
                                # ✅ Semantic cached code validated successfully
                                logger.info(f"✅ Semantic cached code validated successfully!")

                                # Add selection info to semantic cache metadata
                                semantic_cache_metadata['selected_match'] = {
                                    'score': round(best_match['score'], 3),
                                    'node_action': best_match['node_action'],
                                    'reason': 'best_score',
                                    'key_validation': validation_reason,
                                    'output_validation': 'passed',
                                    'execution_time_ms': round(execution_time_ms, 2)
                                }
                                semantic_cache_metadata['cache_hit'] = True

                                # Clean result
                                clean_result = {k: v for k, v in result.items() if not k.startswith('_')}

                                # Update context_manager
                                context_manager.update(clean_result)

                                # Build metadata
                                metadata = {
                                    'cache_metadata': {
                                        'cache_hit': True,
                                        'cache_type': 'semantic',
                                        'similarity_score': best_match['score'],
                                        'matched_action': best_match['node_action'],
                                        'cost_saved_usd': 0.003  # Estimated AI generation cost
                                    },
                                    'ai_metadata': {
                                        'model': 'semantic_cache',
                                        'generated_code': best_match['code'],
                                        'from_semantic_cache': True,
                                        'semantic_cache_search': semantic_cache_metadata  # ✨ ADD SEARCH METADATA
                                    },
                                    'execution_metadata': {
                                        'stdout': result.get('_stdout', ''),
                                        'stderr': result.get('_stderr', ''),
                                        'exit_code': result.get('_exit_code', 0)
                                    }
                                }

                                logger.info(f"💰 Saved ~$0.003 with semantic cache (score: {best_match['score']:.3f})")
                                return clean_result, metadata

                            else:
                                # Validation failed - fallback to AI generation
                                logger.warning(f"❌ Semantic cached code failed validation:")
                                if validation_result.error_message:
                                    logger.warning(f"   Error: {validation_result.error_message}")
                                for warning in validation_result.warnings:
                                    logger.warning(f"   Warning: {warning}")
                                logger.info(f"🔄 Falling back to AI generation")

                                # Record validation failure in metadata
                                validation_errors = [validation_result.error_message] if validation_result.error_message else []
                                validation_errors.extend(validation_result.warnings)

                                semantic_cache_metadata['selected_match'] = {
                                    'score': round(best_match['score'], 3),
                                    'node_action': best_match['node_action'],
                                    'reason': 'best_score',
                                    'key_validation': validation_reason,
                                    'output_validation': 'failed',
                                    'validation_errors': validation_errors
                                }
                                semantic_cache_metadata['cache_hit'] = False
                                semantic_cache_metadata['fallback_reason'] = 'output_validation_failed'

                        except Exception as e:
                            logger.warning(f"⚠️  Semantic cached code execution failed: {e}")
                            logger.info(f"🔄 Falling back to AI generation")

                            # Record execution failure in metadata
                            semantic_cache_metadata['selected_match'] = {
                                'score': round(best_match['score'], 3),
                                'node_action': best_match['node_action'],
                                'reason': 'best_score',
                                'key_validation': validation_reason,
                                'execution_error': str(e)
                            }
                            semantic_cache_metadata['cache_hit'] = False
                            semantic_cache_metadata['fallback_reason'] = 'execution_failed'
                    else:
                        # Can't use cached code due to missing keys
                        semantic_cache_metadata['selected_match'] = {
                            'score': round(best_match['score'], 3),
                            'node_action': best_match['node_action'],
                            'reason': 'skipped',
                            'key_validation': validation_reason
                        }
                        semantic_cache_metadata['cache_hit'] = False
                        semantic_cache_metadata['fallback_reason'] = 'missing_required_keys'

                else:
                    logger.info(f"🔍 No semantic cache matches above threshold 0.85")
                    # Record that no matches were found
                    semantic_cache_metadata['cache_hit'] = False
                    semantic_cache_metadata['fallback_reason'] = 'no_matches_above_threshold'

            except Exception as e:
                logger.warning(f"Semantic cache search failed: {e}. Continuing with AI generation.")
                # Record search error
                if semantic_cache_metadata is None:
                    semantic_cache_metadata = {}
                semantic_cache_metadata['search_error'] = str(e)
                semantic_cache_metadata['cache_hit'] = False
                semantic_cache_metadata['fallback_reason'] = 'search_failed'

        # ═══════════════════════════════════════════════════════
        # CACHE MISS - Generate with AI
        # ═══════════════════════════════════════════════════════
        try:
            # Pasar context_manager al orchestrator
            result, updated_context_manager = await self.orchestrator.execute_workflow(
                task=prompt_task,
                context=context,
                timeout=timeout,
                node_type=node_type,
                node_id=node_id,
                context_manager=context_manager
            )

            # ═══════════════════════════════════════════════════════
            # SEPARAR METADATA DEL RESULTADO
            # ═══════════════════════════════════════════════════════
            ai_metadata = result.get('_ai_metadata', {})
            execution_failed = ai_metadata.get('status') == 'failed' or ai_metadata.get('final_error')

            # Extraer stdout/stderr para execution_metadata
            stdout = result.get('_stdout', '')
            stderr = result.get('_stderr', '')
            exit_code = result.get('_exit_code', 0)

            # Limpiar result de campos internos
            clean_result = {k: v for k, v in result.items() if not k.startswith('_')}

            # ═══════════════════════════════════════════════════════
            # SAVE TO CACHE (if enabled and execution successful)
            # ═══════════════════════════════════════════════════════
            cache_metadata = {}

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

                        cache_metadata = {
                            'cache_hit': False,
                            'cache_key': cache_key_inicial[:16] + "...",
                            'saved_for_future': True
                        }

                        logger.info(f"💾 Code saved to cache for future reuse (code length: {len(generated_code)} chars)")

                        # Save to semantic cache (async, don't await - run in background)
                        if self.semantic_cache and not execution_failed and cache_ctx:
                            try:
                                await self._save_to_semantic_cache(
                                    code=generated_code,
                                    task=prompt_task,
                                    node=node,
                                    context=context,
                                    result=result,
                                    cache_context=cache_ctx
                                )
                            except Exception as e:
                                logger.warning(f"Failed to save to semantic cache: {e}")

                    else:
                        logger.warning(f"⚠️  No generated code found in code_generation metadata, skipping cache save")
                        logger.warning(f"   code_generation keys: {list(code_gen_meta.keys())}")

                except Exception as e:
                    logger.error(f"❌ Failed to save to cache: {e}")
                    import traceback
                    logger.error(traceback.format_exc())

            elif self.cache_manager and execution_failed:
                logger.info(f"🚫 Not caching (execution failed)")

            # ═══════════════════════════════════════════════════════
            # BUILD METADATA DICT
            # ═══════════════════════════════════════════════════════
            # Add semantic cache metadata to ai_metadata (if search was performed)
            if semantic_cache_metadata:
                ai_metadata['semantic_cache_search'] = semantic_cache_metadata

            metadata = {
                'ai_metadata': ai_metadata,
                'execution_metadata': {
                    'stdout': stdout,
                    'stderr': stderr,
                    'exit_code': exit_code
                }
            }

            if cache_metadata:
                metadata['cache_metadata'] = cache_metadata

            # ═══════════════════════════════════════════════════════
            # UPDATE CONTEXT MANAGER
            # ═══════════════════════════════════════════════════════
            context_manager.update(clean_result)

            logger.info(f"✅ Multi-Agent execution completed successfully")
            return clean_result, metadata

        except Exception as e:
            logger.error(f"❌ Multi-Agent execution failed: {e}")
            raise ExecutorError(f"Multi-Agent execution failed: {e}")

    def _build_semantic_query(
        self,
        task: str,
        node: Optional[Dict[str, Any]],
        cache_context: Dict[str, Any]
    ) -> str:
        """
        Build semantic search query from task and input schema.

        Simplified to only use:
        - Prompt (task description)
        - Full input schema (no filtering)

        Args:
            task: Natural language task/prompt
            node: Optional node dictionary (unused now)
            cache_context: Cache context from GraphEngine

        Returns:
            Formatted search query string
        """
        import json

        parts = []

        # Prompt (task description)
        parts.append(f"Prompt: {task}")

        # Input schema (full, unfiltered)
        input_schema = cache_context.get('input_schema', {})
        if input_schema:
            schema_str = json.dumps(input_schema, indent=2, sort_keys=True)
            parts.append(f"Input Schema:\n{schema_str}")

        return "\n\n".join(parts)

    def _extract_imports(self, code: str) -> List[str]:
        """
        Extract library names from Python code imports.

        Args:
            code: Python source code

        Returns:
            List of imported library names

        Example:
            >>> code = "import fitz\\nfrom PIL import Image\\nimport base64"
            >>> libs = _extract_imports(code)
            >>> libs
            ['fitz', 'PIL', 'base64']
        """
        import re

        libraries = []

        # Find "import X" statements
        import_pattern = r'^import\s+([a-zA-Z0-9_]+)'
        for match in re.finditer(import_pattern, code, re.MULTILINE):
            libraries.append(match.group(1))

        # Find "from X import Y" statements
        from_pattern = r'^from\s+([a-zA-Z0-9_]+)\s+import'
        for match in re.finditer(from_pattern, code, re.MULTILINE):
            libraries.append(match.group(1))

        # Remove duplicates and return
        return list(set(libraries))

    def _extract_required_context_keys(self, code: str) -> List[str]:
        """
        Extract context keys that the code actually uses.

        This analyzes the generated code to find all context['key'] accesses,
        which is critical for semantic cache filtering.

        Args:
            code: Python source code

        Returns:
            List of context keys used in the code

        Example:
            >>> code = "total = context['amount']\\npdf = context.get('pdf_data')"
            >>> keys = _extract_required_context_keys(code)
            >>> keys
            ['amount', 'pdf_data']
        """
        import re

        required_keys = set()

        # Pattern 1: context['key']
        pattern1 = r"context\['([^']+)'\]"
        for match in re.finditer(pattern1, code):
            required_keys.add(match.group(1))

        # Pattern 2: context["key"]
        pattern2 = r'context\["([^"]+)"\]'
        for match in re.finditer(pattern2, code):
            required_keys.add(match.group(1))

        # Pattern 3: context.get('key')
        pattern3 = r"context\.get\('([^']+)'"
        for match in re.finditer(pattern3, code):
            required_keys.add(match.group(1))

        # Pattern 4: context.get("key")
        pattern4 = r'context\.get\("([^"]+)"'
        for match in re.finditer(pattern4, code):
            required_keys.add(match.group(1))

        return sorted(list(required_keys))

    async def _generate_code_description(
        self,
        code: str,
        task: str,
        cache_context: Dict[str, Any]
    ) -> str:
        """
        Generate natural language description of what the code does.

        Uses a lightweight LLM call to create a concise technical description.

        Args:
            code: The Python code to describe
            task: Original task/prompt
            cache_context: Cache context with schema and insights

        Returns:
            2-3 sentence technical description

        Example:
            "Extracts text from PDF using PyMuPDF. Works with standard PDFs (not scanned).
             Returns plain text without formatting."
        """
        import json
        from openai import AsyncOpenAI
        import os

        try:
            client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

            prompt = f"""Describe what this code does in 2-3 technical sentences.

Code:
```python
{code}
```

Task: {task}

Input schema: {json.dumps(cache_context.get('input_schema', {}), indent=2)}

Context: {', '.join(cache_context.get('insights', []))}

Format:
- Main functionality
- Libraries/techniques used
- Important requirements or limitations

Example: "Extracts text from PDF using PyMuPDF. Works with standard PDFs (not scanned). Returns plain text without formatting."
"""

            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a technical documentation assistant. Be concise and precise."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=150
            )

            description = response.choices[0].message.content.strip()
            logger.debug(f"Generated code description: {description[:60]}...")

            return description

        except Exception as e:
            logger.warning(f"Failed to generate code description: {e}")
            # Fallback to simple description
            return f"Executes task: {task[:100]}"

    async def _save_to_semantic_cache(
        self,
        code: str,
        task: str,
        node: Optional[Dict[str, Any]],
        context: Dict[str, Any],
        result: Dict[str, Any],
        cache_context: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Save successful code execution to semantic cache.

        Args:
            code: The generated Python code
            task: Original task/prompt
            node: Optional node dictionary
            context: Execution context
            result: Execution result (must be successful)
            cache_context: Optional cache context for semantic matching
        """
        if not self.semantic_cache:
            return

        try:
            if not cache_context:
                logger.debug("No cache_context provided, skipping semantic cache save")
                return

            # Extract libraries
            libraries_used = self._extract_imports(code)

            # Extract required context keys from code (for validation, not for search)
            required_keys = self._extract_required_context_keys(code)

            # Get FULL input schema (no filtering)
            full_input_schema = cache_context.get('input_schema', {})

            logger.debug(f"Required keys extracted from code: {required_keys}")
            logger.debug(f"Saving with FULL input_schema: {list(full_input_schema.keys())}")

            # Save to cache
            success = self.semantic_cache.save_code(
                ai_description=task,  # Save prompt as-is, no AI generation
                input_schema=full_input_schema,  # Use FULL schema, not filtered
                insights=[],  # Empty, we don't save insights anymore
                config=cache_context.get('config', {}),
                code=code,
                node_action=node.get('id', 'unknown') if node else 'unknown',
                node_description=node.get('description', task[:100]) if node else task[:100],
                libraries_used=libraries_used,
                required_keys=required_keys  # Save for validation later
            )

            if success:
                logger.info(f"✓ Code saved to semantic cache")
                logger.debug(f"  Prompt: {task[:60]}...")
                logger.debug(f"  Libraries: {', '.join(libraries_used)}")
                logger.debug(f"  Required keys: {required_keys}")
            else:
                logger.warning(f"Failed to save code to semantic cache")

        except Exception as e:
            logger.error(f"Error saving to semantic cache: {e}")
            # Don't raise - semantic cache save is optional


class AIExecutor(ExecutorStrategy):
    """
    Phase 2: Always generates fresh code using LLM.

    NOT IMPLEMENTED YET - Placeholder for Phase 2.
    """

    async def execute(
        self,
        code: str,
        context: Dict[str, Any],
        context_manager: Optional['ContextManager'] = None,
        timeout: Optional[int] = None,
        workflow: Optional[Dict[str, Any]] = None,
        node: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
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
        context_manager: Optional['ContextManager'] = None,
        timeout: Optional[int] = None,
        workflow: Optional[Dict[str, Any]] = None,
        node: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Execute code in E2B cloud sandbox with circuit breaker protection.

        Args:
            code: Python code to execute
            context: Current workflow context (dict)
            context_manager: Optional ContextManager (unused by E2BExecutor)
            timeout: Execution timeout in seconds
            workflow: Optional workflow definition (unused by E2BExecutor)
            node: Optional node definition (unused by E2BExecutor)
            **kwargs: Additional executor-specific parameters

        Returns:
            Tuple containing:
            - result (Dict): Functional output (clean, no metadata)
            - metadata (Dict): Execution metadata (stdout, stderr, exit_code)

        Side effects:
            - If context_manager provided, updates it with functional result

        Raises:
            E2BConnectionError: If circuit breaker is open or E2B unreachable
            E2BTimeoutError: If execution exceeds timeout
            CodeExecutionError: If user code has syntax/runtime errors
            E2BSandboxError: If sandbox crashes or other E2B error
        """
        # Default timeout if not provided
        if timeout is None:
            timeout = 30
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
            # _execute_sync now returns (result, stdout, stderr, exit_code)
            result, stdout, stderr, exit_code = await loop.run_in_executor(None, self._execute_sync, full_code, timeout)

            # Record success in circuit breaker
            e2b_circuit_breaker.record_success()

            # Build metadata
            metadata = {
                'execution_metadata': {
                    'stdout': stdout,
                    'stderr': stderr,
                    'exit_code': exit_code
                }
            }

            # Update context_manager if provided
            if context_manager:
                context_manager.update(result)

            return result, metadata

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

    def _execute_sync(self, full_code: str, timeout: int) -> Tuple[Dict[str, Any], str, str, int]:
        """
        Synchronous execution wrapper for E2B v2.x SDK.

        Args:
            full_code: Code with context injection
            timeout: Execution timeout in seconds

        Returns:
            Tuple containing:
            - result (Dict): Updated context dictionary
            - stdout (str): Standard output from execution
            - stderr (str): Standard error from execution
            - exit_code (int): Exit code from execution

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

                # Return tuple: (result, stdout, stderr, exit_code)
                return updated_context, stdout_output, execution.stderr or "", execution.exit_code

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
