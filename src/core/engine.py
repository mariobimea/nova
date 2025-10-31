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

from .nodes import create_node_from_dict, NodeType, StartNode, EndNode, ActionNode, DecisionNode
from .executors import get_executor
from .context import ContextManager
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
        # Read decision result from context
        decision_result = context.get("branch_decision")

        if decision_result is None:
            raise GraphExecutionError(
                f"DecisionNode {current_node_id} did not set 'branch_decision' in context"
            )

        # Find edge matching the decision
        # Convert boolean to string for comparison
        decision_str = "true" if decision_result else "false"

        for edge in outgoing_edges:
            if edge.get("condition") == decision_str:
                return edge["to"]

        raise GraphExecutionError(
            f"No edge found for decision result '{decision_str}' from node {current_node_id}"
        )

    async def _execute_node(
        self,
        node: NodeType,
        context: ContextManager,
        execution_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Execute a single node and return execution metadata.

        Args:
            node: Node to execute
            context: Current workflow context
            execution_id: Optional execution ID for chain_of_work logging

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
                # ActionNode: Execute code, update context
                executor = get_executor(node.executor, api_key=self.api_key)

                updated_context = await executor.execute(
                    code=node.code,
                    context=context.get_all(),
                    timeout=node.timeout
                )

                context.update(updated_context)
                metadata["code_executed"] = node.code

            elif isinstance(node, DecisionNode):
                # DecisionNode: Execute code, read decision, store for branching
                executor = get_executor("e2b", api_key=self.api_key)

                updated_context = await executor.execute(
                    code=node.code,
                    context=context.get_all(),
                    timeout=node.timeout
                )

                context.update(updated_context)
                metadata["code_executed"] = node.code

                # Extract decision result
                decision_result = context.get("branch_decision")
                if decision_result is None:
                    raise GraphExecutionError(
                        f"DecisionNode {node.id} must set 'branch_decision' in context"
                    )

                metadata["decision_result"] = "true" if decision_result else "false"

            else:
                raise GraphExecutionError(f"Unknown node type: {type(node)}")

        except (ExecutorError, E2BSandboxError, E2BTimeoutError, CodeExecutionError) as e:
            # Code execution failed in sandbox
            metadata["status"] = "failed"
            metadata["error_message"] = str(e)
            logger.error(f"Node {node.id} execution failed: {e}")
            raise GraphExecutionError(f"Node {node.id} failed: {e}")

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
        workflow_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Execute a complete workflow.

        Args:
            workflow_definition: Workflow JSON with nodes and edges
            initial_context: Initial context data (default: {})
            workflow_id: Workflow ID for persisting execution (required if db_session is set)

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

        # Create Execution record if persistence is enabled
        execution = None
        if self.db_session and workflow_id:
            from ..models.execution import Execution
            execution = Execution(
                workflow_id=workflow_id,
                status='running',
                started_at=datetime.utcnow()
            )
            self.db_session.add(execution)
            self.db_session.commit()
            logger.info(f"Created Execution record with ID: {execution.id}")

        # Parse and validate workflow
        nodes, edges = self._parse_workflow(workflow_definition)
        self._validate_graph(nodes, edges)

        # Initialize context
        context = ContextManager(initial_context or {})

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
                metadata = await self._execute_node(current_node, context, execution.id if execution else None)
                execution_trace.append(metadata)

                # Persist to ChainOfWork if db_session is available
                if self.db_session and execution:
                    from ..models.chain_of_work import ChainOfWork
                    chain_entry = ChainOfWork(
                        execution_id=execution.id,
                        node_id=metadata['node_id'],
                        node_type=metadata['node_type'],
                        code_executed=metadata.get('code_executed'),
                        input_context=metadata['input_context'],
                        output_result=metadata['output_result'],
                        execution_time=metadata['execution_time'],
                        status=metadata['status'],
                        error_message=metadata.get('error_message'),
                        decision_result=metadata.get('decision_result'),
                        path_taken=metadata.get('path_taken'),
                        timestamp=datetime.utcnow()
                    )
                    self.db_session.add(chain_entry)
                    self.db_session.commit()

            except GraphExecutionError as e:
                logger.error(f"Workflow execution failed at node {current_node_id}: {e}")

                # Create metadata for the failed node
                failed_metadata = {
                    "node_id": current_node_id,
                    "node_type": current_node.type,
                    "status": "failed",
                    "error_message": str(e),
                    "input_context": context.snapshot(),
                    "output_result": context.snapshot(),
                    "execution_time": 0,
                    "code_executed": getattr(current_node, 'code', None),
                    "decision_result": None,
                    "path_taken": None
                }
                execution_trace.append(failed_metadata)

                # Persist failed node to ChainOfWork
                if self.db_session and execution:
                    from ..models.chain_of_work import ChainOfWork
                    chain_entry = ChainOfWork(
                        execution_id=execution.id,
                        node_id=failed_metadata['node_id'],
                        node_type=failed_metadata['node_type'],
                        code_executed=failed_metadata.get('code_executed'),
                        input_context=failed_metadata['input_context'],
                        output_result=failed_metadata['output_result'],
                        execution_time=failed_metadata['execution_time'],
                        status=failed_metadata['status'],
                        error_message=failed_metadata.get('error_message'),
                        decision_result=failed_metadata.get('decision_result'),
                        path_taken=failed_metadata.get('path_taken'),
                        timestamp=datetime.utcnow()
                    )
                    self.db_session.add(chain_entry)

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
