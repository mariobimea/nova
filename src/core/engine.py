"""
Graph Engine for NOVA Workflow System

The GraphEngine is responsible for:
1. Loading workflow definitions (JSON → Node objects)
2. Validating graph structure (single start, edges valid, no orphan nodes)
3. Executing workflows node by node
4. Managing context between nodes
5. Handling decision branching
6. Recording execution trace to Chain of Work

Example workflow execution:
    engine = GraphEngine()  # Uses E2B cloud sandbox by default

    result = await engine.execute_workflow(
        workflow_definition={
            "nodes": [...],
            "edges": [...]
        },
        initial_context={"input": "data"}
    )
"""

import logging
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import time
import json

from sqlalchemy.orm import Session


def make_json_serializable(obj):
    """
    Recursively convert non-JSON-serializable objects to serializable format.

    Handles:
    - datetime → ISO 8601 string
    - bytes → base64 string (for binary data)
    - sets → lists
    - custom objects → str(obj)
    """
    import base64

    if isinstance(obj, dict):
        return {k: make_json_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [make_json_serializable(item) for item in obj]
    elif isinstance(obj, tuple):
        return [make_json_serializable(item) for item in obj]
    elif isinstance(obj, set):
        return [make_json_serializable(item) for item in obj]
    elif isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, bytes):
        # Base64 encode binary data
        return base64.b64encode(obj).decode('ascii')
    elif hasattr(obj, '__dict__'):
        # Custom objects → convert to string
        return str(obj)
    else:
        return obj

from .nodes import create_node_from_dict, NodeType, StartNode, EndNode, ActionNode, DecisionNode
from .executors import get_executor
from .context import ContextManager
from .schema_extractor import build_cache_context
from .exceptions import (
    GraphValidationError,
    GraphExecutionError,
    ExecutorError,
    E2BSandboxError,
    E2BTimeoutError,
    CodeExecutionError
)

logger = logging.getLogger(__name__)


class GraphEngine:
    """
    Core execution engine for workflow graphs.

    The GraphEngine orchestrates workflow execution by:
    - Parsing workflow definitions into Node objects
    - Validating graph structure
    - Executing nodes in the correct order
    - Managing shared context between nodes
    - Handling decision branching
    - Recording execution trace
    """

    def __init__(self, api_key: Optional[str] = None, db_session: Optional[Session] = None):
        """
        Initialize GraphEngine.

        Args:
            api_key: E2B API key (optional, reads from E2B_API_KEY env var if not provided)
            db_session: SQLAlchemy session for persisting executions (optional)
        """
        self.api_key = api_key
        self.db_session = db_session
        logger.info(f"GraphEngine initialized with E2B cloud sandbox (persistence: {'enabled' if db_session else 'disabled'})")

    def _parse_workflow(self, workflow_definition: Dict[str, Any]) -> Tuple[Dict[str, NodeType], List[Dict[str, str]]]:
        """
        Parse workflow definition into Node objects.

        Args:
            workflow_definition: Dict with "nodes" and "edges" keys

        Returns:
            Tuple of (nodes_dict, edges_list)
            - nodes_dict: {node_id: Node object}
            - edges_list: [{"from": "node1", "to": "node2", "condition": "true"}]

        Raises:
            GraphValidationError: If parsing fails
        """
        if "nodes" not in workflow_definition:
            raise GraphValidationError("Workflow definition missing 'nodes' field")

        if "edges" not in workflow_definition:
            raise GraphValidationError("Workflow definition missing 'edges' field")

        # Parse nodes
        nodes = {}
        for node_data in workflow_definition["nodes"]:
            try:
                node = create_node_from_dict(node_data)
                nodes[node.id] = node
            except Exception as e:
                raise GraphValidationError(f"Failed to parse node {node_data.get('id')}: {e}")

        edges = workflow_definition["edges"]

        logger.info(f"Parsed workflow: {len(nodes)} nodes, {len(edges)} edges")
        return nodes, edges

    def _validate_graph(self, nodes: Dict[str, NodeType], edges: List[Dict[str, str]]) -> None:
        """
        Validate graph structure.

        Checks:
        1. Exactly one StartNode
        2. At least one EndNode
        3. All edges reference existing nodes
        4. No duplicate node IDs (already guaranteed by dict)

        Args:
            nodes: Dictionary of node_id -> Node
            edges: List of edge definitions

        Raises:
            GraphValidationError: If validation fails
        """
        # Check for exactly one StartNode
        start_nodes = [n for n in nodes.values() if isinstance(n, StartNode)]
        if len(start_nodes) == 0:
            raise GraphValidationError("Workflow must have exactly one StartNode (found 0)")
        if len(start_nodes) > 1:
            raise GraphValidationError(f"Workflow must have exactly one StartNode (found {len(start_nodes)})")

        # Check for at least one EndNode
        end_nodes = [n for n in nodes.values() if isinstance(n, EndNode)]
        if len(end_nodes) == 0:
            raise GraphValidationError("Workflow must have at least one EndNode")

        # Validate edges reference existing nodes
        for edge in edges:
            from_id = edge.get("from")
            to_id = edge.get("to")

            if not from_id or not to_id:
                raise GraphValidationError(f"Edge missing 'from' or 'to': {edge}")

            if from_id not in nodes:
                raise GraphValidationError(f"Edge references non-existent node: {from_id}")

            if to_id not in nodes:
                raise GraphValidationError(f"Edge references non-existent node: {to_id}")

        logger.info("Graph validation passed")

    def _find_next_node(
        self,
        current_node_id: str,
        edges: List[Dict[str, str]],
        context: ContextManager
    ) -> Optional[str]:
        """
        Find the next node to execute based on current node and edges.

        For ActionNode/StartNode: Follow the single outgoing edge
        For DecisionNode: Follow edge based on decision result in context

        Args:
            current_node_id: ID of current node
            edges: List of all edges
            context: Current workflow context (for decision branching)

        Returns:
            Next node ID, or None if no edge found (EndNode)

        Raises:
            GraphExecutionError: If decision branching logic fails
        """
        # Find edges from current node
        outgoing_edges = [e for e in edges if e["from"] == current_node_id]

        if len(outgoing_edges) == 0:
            # No outgoing edges (likely EndNode)
            return None

        if len(outgoing_edges) == 1:
            # Single edge (ActionNode, StartNode, or EndNode)
            return outgoing_edges[0]["to"]

        # Multiple edges (DecisionNode branching)
        # Read decision result from context using node-specific key
        # This prevents conflicts when multiple DecisionNodes exist in the workflow
        # Note: node_id already contains descriptive name (e.g., "has_pdf_decision")
        decision_key = current_node_id
        decision_result = context.get(decision_key)

        if decision_result is None:
            raise GraphExecutionError(
                f"DecisionNode {current_node_id} did not set '{decision_key}' in context"
            )

        # Convert decision result to string for edge matching
        # Supports both boolean (True/False) and string ('true'/'false', 'yes'/'no', etc.)
        if isinstance(decision_result, bool):
            decision_str = "true" if decision_result else "false"
        elif isinstance(decision_result, str):
            decision_str = decision_result.lower()
        else:
            raise GraphExecutionError(
                f"DecisionNode {current_node_id} set '{decision_key}' to unsupported type: "
                f"{type(decision_result).__name__} = {decision_result}. Expected bool or str."
            )

        for edge in outgoing_edges:
            if edge.get("condition") == decision_str:
                return edge["to"]

        raise GraphExecutionError(
            f"No edge found for decision result '{decision_str}' from node {current_node_id}. "
            f"Available conditions: {[e.get('condition') for e in outgoing_edges]}"
        )

    async def _execute_node(
        self,
        node: NodeType,
        context: ContextManager,
        workflow_definition: Dict[str, Any],
        execution_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Execute a single node and return execution metadata.

        Args:
            node: Node to execute
            context: Current workflow context
            workflow_definition: Complete workflow definition (for model resolution)
            execution_id: Optional execution ID for chain_of_work logging

        Note:
            cache_context is built dynamically inside this method for each ActionNode
            to ensure it reflects the current state of the context.

        Returns:
            Execution metadata dict with:
            - node_id, node_type, status, execution_time
            - input_context, output_result
            - code_executed (for ActionNode/DecisionNode)
            - decision_result, path_taken (for DecisionNode)

        Raises:
            GraphExecutionError: If node execution fails
        """
        start_time = time.time()
        input_context = context.snapshot()  # Deep copy for chain_of_work

        metadata = {
            "node_id": node.id,
            "node_type": node.type,
            "input_context": input_context,
            "status": "success",
            "error_message": None,
            "code_executed": None,
            "decision_result": None,
            "path_taken": None,
        }

        logger.info(f"Executing node: {node.id} ({node.type})")

        try:
            if isinstance(node, StartNode):
                # StartNode: No execution, just pass through
                pass

            elif isinstance(node, EndNode):
                # EndNode: No execution, just pass through
                pass

            elif isinstance(node, ActionNode):
                # ActionNode: Execute code or prompt, update context
                executor = get_executor(
                    node.executor,
                    api_key=self.api_key,
                    db_session=self.db_session  # Pass db_session for CachedExecutor
                )

                # Detect if node uses prompt (AI) or code (hardcoded)
                # CachedExecutor expects prompts, E2BExecutor expects code
                if node.executor == "cached":
                    # AI-powered executor: uses natural language prompts
                    code_or_prompt = getattr(node, 'prompt', None)
                    if not code_or_prompt:
                        raise GraphExecutionError(
                            f"ActionNode {node.id} with executor='cached' must have 'prompt' attribute"
                        )
                else:
                    # Traditional executor: uses hardcoded Python code
                    code_or_prompt = node.code
                    if not code_or_prompt:
                        raise GraphExecutionError(
                            f"ActionNode {node.id} must have 'code' attribute"
                        )

                # Rebuild cache_context with current context state
                # (context may have new keys added by previous nodes)
                current_cache_context = build_cache_context(context.get_all())
                logger.debug(f"🔄 Rebuilt cache context for node {node.id}: {len(current_cache_context.get('input_schema', {}))} schema fields")

                # Execute code/prompt - all executors now return (result, metadata)
                result, exec_metadata = await executor.execute(
                    code=code_or_prompt,
                    context=context.get_all(),
                    context_manager=context,  # Pass by reference (CachedExecutor updates in-place)
                    timeout=node.timeout,
                    workflow=workflow_definition,
                    node={"id": node.id, "type": "action", "model": getattr(node, "model", None)},
                    cache_context=current_cache_context  # Pass CURRENT cache_context (not initial)
                )

                # DEBUG: Log what executor returned
                logger.info(f"🔍 DEBUG after executor.execute() for node {node.id}:")
                logger.info(f"   Executor type: {node.executor}")
                logger.info(f"   result keys: {list(result.keys())}")
                logger.info(f"   metadata keys: {list(exec_metadata.keys())}")

                # Store metadata - merge all metadata fields
                if exec_metadata:
                    # exec_metadata structure: {cache_metadata, ai_metadata, execution_metadata}
                    # We want to store it all in metadata["ai_metadata"] but flatten it
                    metadata["ai_metadata"] = exec_metadata.get("ai_metadata", {})

                    # Also store cache and execution metadata at top level
                    if "cache_metadata" in exec_metadata:
                        metadata["ai_metadata"]["_cache_metadata"] = exec_metadata["cache_metadata"]
                    if "execution_metadata" in exec_metadata:
                        metadata["ai_metadata"]["_execution_metadata"] = exec_metadata["execution_metadata"]

                # Update context with functional result (clean, no metadata)
                logger.info(f"🔍 DEBUG before context.update() for node {node.id}:")
                logger.info(f"   result keys: {list(result.keys())}")
                logger.info(f"   context BEFORE update: {list(context.get_all().keys())}")

                context.update(result)

                logger.info(f"   context AFTER update: {list(context.get_all().keys())}")
                logger.info(f"   Did context gain new keys? {set(context.get_all().keys()) - set(input_context.keys())}")

                # Store executed code
                if exec_metadata and "ai_metadata" in exec_metadata and "generated_code" in exec_metadata["ai_metadata"]:
                    metadata["code_executed"] = exec_metadata["ai_metadata"]["generated_code"]
                else:
                    metadata["code_executed"] = code_or_prompt

            elif isinstance(node, DecisionNode):
                # DecisionNode: Execute code or prompt for decision, read result, store for branching
                executor = get_executor(
                    node.executor,
                    api_key=self.api_key,
                    db_session=self.db_session  # Pass db_session for CachedExecutor
                )

                # Detect if node uses prompt (AI) or code (hardcoded)
                if node.executor == "cached":
                    # AI-powered executor: uses natural language prompts
                    code_or_prompt = getattr(node, 'prompt', None)
                    if not code_or_prompt:
                        raise GraphExecutionError(
                            f"DecisionNode {node.id} with executor='cached' must have 'prompt' attribute"
                        )
                else:
                    # Traditional executor: uses hardcoded Python code
                    code_or_prompt = node.code
                    if not code_or_prompt:
                        raise GraphExecutionError(
                            f"DecisionNode {node.id} must have 'code' attribute"
                        )

                # Execute code/prompt - all executors now return (result, metadata)
                result, exec_metadata = await executor.execute(
                    code=code_or_prompt,
                    context=context.get_all(),
                    context_manager=context,  # Pass by reference (CachedExecutor updates in-place)
                    timeout=node.timeout,
                    workflow=workflow_definition,
                    node={"id": node.id, "type": "decision", "model": getattr(node, "model", None)}
                )

                # Store metadata - merge all metadata fields
                if exec_metadata:
                    # exec_metadata structure: {cache_metadata, ai_metadata, execution_metadata}
                    # We want to store it all in metadata["ai_metadata"] but flatten it
                    metadata["ai_metadata"] = exec_metadata.get("ai_metadata", {})

                    # Also store cache and execution metadata at top level
                    if "cache_metadata" in exec_metadata:
                        metadata["ai_metadata"]["_cache_metadata"] = exec_metadata["cache_metadata"]
                    if "execution_metadata" in exec_metadata:
                        metadata["ai_metadata"]["_execution_metadata"] = exec_metadata["execution_metadata"]

                # Update context with functional result (clean, no metadata)
                context.update(result)

                # Store executed code
                if exec_metadata and "ai_metadata" in exec_metadata and "generated_code" in exec_metadata["ai_metadata"]:
                    metadata["code_executed"] = exec_metadata["ai_metadata"]["generated_code"]
                else:
                    metadata["code_executed"] = code_or_prompt

                # Extract decision result
                # The executor MUST set node_id in context
                # Note: node_id already contains descriptive name (e.g., "has_pdf_decision")
                decision_key = node.id
                decision_result = context.get(decision_key)

                if decision_result is None:
                    # NO FALLBACK: Si el executor no agregó node_id, es un error
                    error_msg = (
                        f"DecisionNode {node.id} did not set '{decision_key}' in context. "
                        f"Available context keys: {list(context.get_all().keys())}"
                    )
                    logger.error(error_msg)
                    raise GraphExecutionError(error_msg)

                # Convert decision result to string for edge matching
                # Supports both boolean (True/False) and string ('true'/'false', 'yes'/'no', etc.)
                if isinstance(decision_result, bool):
                    decision_str = "true" if decision_result else "false"
                elif isinstance(decision_result, str):
                    decision_str = decision_result.lower()
                else:
                    error_msg = (
                        f"DecisionNode {node.id} set '{decision_key}' to unsupported type: "
                        f"{type(decision_result).__name__} = {decision_result}. "
                        f"Expected bool or str."
                    )
                    logger.error(error_msg)
                    raise GraphExecutionError(error_msg)

                metadata["decision_result"] = decision_str

            else:
                raise GraphExecutionError(f"Unknown node type: {type(node)}")

        except (ExecutorError, E2BSandboxError, E2BTimeoutError, CodeExecutionError) as e:
            # Code execution failed in sandbox
            metadata["status"] = "failed"
            metadata["error_message"] = str(e)
            logger.error(f"Node {node.id} execution failed: {e}")
            raise GraphExecutionError(f"Node {node.id} failed: {e}") from e

        except Exception as e:
            # Unexpected error
            metadata["status"] = "failed"
            metadata["error_message"] = str(e)
            logger.error(f"Unexpected error executing node {node.id}: {e}")
            raise GraphExecutionError(f"Unexpected error in node {node.id}: {e}")

        finally:
            execution_time = time.time() - start_time
            metadata["execution_time"] = execution_time
            metadata["output_result"] = context.snapshot()

            logger.info(f"Node {node.id} completed in {execution_time:.3f}s (status: {metadata['status']})")

        return metadata

    async def execute_workflow(
        self,
        workflow_definition: Dict[str, Any],
        initial_context: Optional[Dict[str, Any]] = None,
        workflow_id: Optional[int] = None,
        execution_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Execute a complete workflow.

        Args:
            workflow_definition: Workflow JSON with nodes and edges
            initial_context: Initial context data (default: {})
            workflow_id: Workflow ID for persisting execution (required if db_session is set)
            execution_id: Existing Execution ID to use (if provided, won't create new one)

        Returns:
            Execution result with:
            - status: "success" or "failed"
            - final_context: Context at workflow end
            - execution_trace: List of node execution metadata
            - execution_id: Database ID of execution (if persisted)
            - error: Error message if failed

        Raises:
            GraphValidationError: If workflow structure is invalid
            GraphExecutionError: If workflow execution fails
        """
        logger.info("Starting workflow execution")

        # Get or create Execution record if persistence is enabled
        execution = None
        if self.db_session and execution_id:
            # Use existing execution (passed from worker)
            from ..models.execution import Execution
            execution = self.db_session.query(Execution).filter(
                Execution.id == execution_id
            ).first()

            if execution:
                logger.info(f"Using existing Execution record with ID: {execution.id}")
            else:
                logger.warning(f"Execution {execution_id} not found, proceeding without persistence")

        elif self.db_session and workflow_id:
            # Create new execution (standalone mode)
            from ..models.execution import Execution
            execution = Execution(
                workflow_id=workflow_id,
                status='running',
                started_at=datetime.utcnow()
            )
            self.db_session.add(execution)
            self.db_session.commit()
            logger.info(f"Created new Execution record with ID: {execution.id}")

        # Parse and validate workflow
        nodes, edges = self._parse_workflow(workflow_definition)
        self._validate_graph(nodes, edges)

        # Initialize context
        context = ContextManager(initial_context or {})

        # NOTE: cache_context is now built dynamically for each node in the execution loop
        # This ensures it reflects the current state of the context (which gets updated after each node)

        # Find start node
        start_node = next(n for n in nodes.values() if isinstance(n, StartNode))
        current_node_id = start_node.id

        # Execution trace (for chain_of_work)
        execution_trace = []

        # Execute nodes sequentially
        max_iterations = len(nodes) * 2  # Prevent infinite loops
        iteration = 0

        while current_node_id is not None:
            iteration += 1
            if iteration > max_iterations:
                raise GraphExecutionError(
                    f"Workflow exceeded max iterations ({max_iterations}). Possible cycle?"
                )

            current_node = nodes[current_node_id]

            # Execute node
            try:
                metadata = await self._execute_node(
                    current_node,
                    context,
                    workflow_definition,
                    execution.id if execution else None
                )
                execution_trace.append(metadata)

                # Persist to ChainOfWork if db_session is available
                if self.db_session and execution:
                    from ..models.chain_of_work import ChainOfWork
                    from ..models.chain_of_work_step import ChainOfWorkStep

                    # Extraer steps si existen (solo CachedExecutor los genera)
                    ai_metadata = metadata.get('ai_metadata', {}) or {}
                    steps_to_persist = ai_metadata.pop('_steps', [])  # Extraer y remover de ai_metadata

                    # 1. Crear entrada principal en ChainOfWork
                    # Convert datetime objects to JSON-serializable format
                    chain_entry = ChainOfWork(
                        execution_id=execution.id,
                        node_id=metadata['node_id'],
                        node_type=metadata['node_type'],
                        code_executed=metadata.get('code_executed'),
                        input_context=make_json_serializable(metadata['input_context']),
                        output_result=make_json_serializable(metadata['output_result']),
                        execution_time=metadata['execution_time'],
                        status=metadata['status'],
                        error_message=metadata.get('error_message'),
                        decision_result=metadata.get('decision_result'),
                        path_taken=metadata.get('path_taken'),
                        ai_metadata=make_json_serializable(ai_metadata),  # Sin _steps
                        timestamp=datetime.utcnow()
                    )
                    self.db_session.add(chain_entry)
                    self.db_session.flush()  # Para obtener chain_entry.id

                    # 2. Crear entradas en ChainOfWorkSteps (si existen)
                    if steps_to_persist:
                        logger.info(f"💾 Guardando {len(steps_to_persist)} steps en ChainOfWorkSteps")

                        step_entries = []
                        for step_data in steps_to_persist:
                            step_entry = ChainOfWorkStep(
                                chain_of_work_id=chain_entry.id,
                                step_number=step_data['step_number'],
                                step_name=step_data['step_name'],
                                agent_name=step_data['agent_name'],
                                attempt_number=step_data['attempt_number'],
                                input_data=step_data.get('input_data'),
                                output_data=step_data.get('output_data'),
                                generated_code=step_data.get('generated_code'),
                                sandbox_id=step_data.get('sandbox_id'),
                                model_used=step_data.get('model_used'),
                                tokens_input=step_data.get('tokens_input'),
                                tokens_output=step_data.get('tokens_output'),
                                cost_usd=step_data.get('cost_usd'),
                                tool_calls=step_data.get('tool_calls'),
                                status=step_data['status'],
                                error_message=step_data.get('error_message'),
                                execution_time_ms=step_data['execution_time_ms'],
                                timestamp=step_data['timestamp']
                            )
                            step_entries.append(step_entry)

                        self.db_session.add_all(step_entries)

                    # 3. Commit todo junto
                    self.db_session.commit()

                    logger.info(
                        f"✅ ChainOfWork guardado: 1 nodo + {len(steps_to_persist)} steps"
                    )

            except GraphExecutionError as e:
                logger.error(f"Workflow execution failed at node {current_node_id}: {e}")

                # ✅ Extract generated code and metadata from ExecutorError if available
                code_to_save = None
                ai_metadata_to_save = None

                # The original ExecutorError is in e.__cause__
                original_error = e.__cause__

                if isinstance(original_error, ExecutorError):
                    # Extract generated code from the last attempt
                    if hasattr(original_error, 'generated_code') and original_error.generated_code:
                        code_to_save = original_error.generated_code
                        logger.info(
                            f"📝 Extracted generated code from failed execution "
                            f"({len(code_to_save)} chars)"
                        )

                    # Extract full history of ALL generation attempts
                    if hasattr(original_error, 'error_history') and original_error.error_history:
                        ai_metadata_to_save = {
                            "model": "gpt-4o-mini",
                            "attempts": len(original_error.error_history),
                            "all_attempts": original_error.error_history,
                            "final_error": str(e),
                            "status": "failed_after_retries"
                        }
                        logger.info(
                            f"📝 Extracted {len(original_error.error_history)} generation attempts "
                            f"from error metadata"
                        )

                # Fallback: If no generated code, use prompt or code from node definition
                if not code_to_save:
                    code_to_save = getattr(current_node, 'prompt', None) or getattr(current_node, 'code', None)
                    if code_to_save:
                        logger.info(f"Using node's original prompt/code as fallback")

                # Create metadata for the failed node
                failed_metadata = {
                    "node_id": current_node_id,
                    "node_type": current_node.type,
                    "status": "failed",
                    "error_message": str(e),
                    "input_context": context.snapshot(),
                    "output_result": context.snapshot(),
                    "execution_time": 0,
                    "code_executed": code_to_save,        # ✅ Generated code or prompt
                    "ai_metadata": ai_metadata_to_save,   # ✅ All attempts with errors
                    "decision_result": None,
                    "path_taken": None
                }
                execution_trace.append(failed_metadata)

                # Persist failed node to ChainOfWork
                if self.db_session and execution:
                    from ..models.chain_of_work import ChainOfWork
                    from ..models.chain_of_work_step import ChainOfWorkStep

                    # Extraer steps si existen (para nodos fallidos también)
                    ai_metadata_failed = failed_metadata.get('ai_metadata', {}) or {}
                    steps_to_persist_failed = ai_metadata_failed.pop('_steps', [])

                    # Convert datetime objects to JSON-serializable format
                    chain_entry = ChainOfWork(
                        execution_id=execution.id,
                        node_id=failed_metadata['node_id'],
                        node_type=failed_metadata['node_type'],
                        code_executed=failed_metadata.get('code_executed'),
                        input_context=make_json_serializable(failed_metadata['input_context']),
                        output_result=make_json_serializable(failed_metadata['output_result']),
                        execution_time=failed_metadata['execution_time'],
                        status=failed_metadata['status'],
                        error_message=failed_metadata.get('error_message'),
                        decision_result=failed_metadata.get('decision_result'),
                        path_taken=failed_metadata.get('path_taken'),
                        ai_metadata=make_json_serializable(ai_metadata_failed),  # Sin _steps
                        timestamp=datetime.utcnow()
                    )
                    self.db_session.add(chain_entry)
                    self.db_session.flush()  # Para obtener chain_entry.id

                    # Persistir steps del nodo fallido (si existen)
                    if steps_to_persist_failed:
                        logger.info(f"💾 Guardando {len(steps_to_persist_failed)} steps del nodo fallido")

                        step_entries = []
                        for step_data in steps_to_persist_failed:
                            step_entry = ChainOfWorkStep(
                                chain_of_work_id=chain_entry.id,
                                step_number=step_data['step_number'],
                                step_name=step_data['step_name'],
                                agent_name=step_data['agent_name'],
                                attempt_number=step_data['attempt_number'],
                                input_data=step_data.get('input_data'),
                                output_data=step_data.get('output_data'),
                                generated_code=step_data.get('generated_code'),
                                sandbox_id=step_data.get('sandbox_id'),
                                model_used=step_data.get('model_used'),
                                tokens_input=step_data.get('tokens_input'),
                                tokens_output=step_data.get('tokens_output'),
                                cost_usd=step_data.get('cost_usd'),
                                tool_calls=step_data.get('tool_calls'),
                                status=step_data['status'],
                                error_message=step_data.get('error_message'),
                                execution_time_ms=step_data['execution_time_ms'],
                                timestamp=step_data['timestamp']
                            )
                            step_entries.append(step_entry)

                        self.db_session.add_all(step_entries)

                    # Update Execution status
                    execution.status = 'failed'
                    execution.error = str(e)
                    execution.completed_at = datetime.utcnow()
                    self.db_session.commit()

                return {
                    "status": "failed",
                    "final_context": context.get_all(),
                    "execution_trace": execution_trace,
                    "execution_id": execution.id if execution else None,
                    "error": str(e),
                    "failed_at_node": current_node_id
                }

            # Check if we reached an EndNode
            if isinstance(current_node, EndNode):
                logger.info(f"Workflow completed at EndNode: {current_node_id}")
                break

            # Find next node
            next_node_id = self._find_next_node(current_node_id, edges, context)

            if next_node_id is None:
                # No more nodes (shouldn't happen if validation passed)
                logger.warning(f"No outgoing edge from node {current_node_id}, stopping execution")
                break

            # Update path_taken for DecisionNode
            if isinstance(current_node, DecisionNode):
                execution_trace[-1]["path_taken"] = next_node_id

                # Update Chain of Work entry with path_taken
                if self.db_session and execution:
                    from ..models.chain_of_work import ChainOfWork
                    # Get the last chain entry (the DecisionNode we just executed)
                    last_chain_entry = self.db_session.query(ChainOfWork).filter(
                        ChainOfWork.execution_id == execution.id,
                        ChainOfWork.node_id == current_node_id
                    ).order_by(ChainOfWork.id.desc()).first()

                    if last_chain_entry:
                        last_chain_entry.path_taken = next_node_id
                        self.db_session.commit()

            current_node_id = next_node_id

        logger.info(f"Workflow execution completed successfully ({iteration} nodes executed)")

        # Update Execution status if persistence is enabled
        if self.db_session and execution:
            execution.status = 'completed'
            execution.result = context.get_all()
            execution.completed_at = datetime.utcnow()
            self.db_session.commit()
            logger.info(f"Execution {execution.id} persisted to database")

        return {
            "status": "success",
            "final_context": context.get_all(),
            "execution_trace": execution_trace,
            "execution_id": execution.id if execution else None,
            "nodes_executed": iteration
        }
