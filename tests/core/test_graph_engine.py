"""
Unit Tests for GraphEngine

Tests cover:
- Workflow parsing and validation
- Graph structure validation (start/end nodes, cycles, orphans)
- Node execution flow
- Decision branching
- Context management between nodes
- Error handling and recovery
- Chain of Work recording
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from src.core.engine import GraphEngine
from src.core.exceptions import GraphValidationError, GraphExecutionError
from src.models.execution import Execution
from src.models.chain_of_work import ChainOfWork


# ============================================================================
# WORKFLOW PARSING TESTS
# ============================================================================

@pytest.mark.unit
def test_parse_workflow_valid(simple_workflow, db_session):
    """Test parsing a valid workflow"""
    engine = GraphEngine(db_session=db_session)

    nodes, edges = engine._parse_workflow(simple_workflow)

    assert len(nodes) == 3
    assert "start" in nodes
    assert "action1" in nodes
    assert "end" in nodes
    assert len(edges) == 2


@pytest.mark.unit
def test_parse_workflow_missing_nodes(db_session):
    """Test parsing fails when 'nodes' field is missing"""
    engine = GraphEngine(db_session=db_session)

    workflow = {"edges": []}

    with pytest.raises(GraphValidationError, match="missing 'nodes'"):
        engine._parse_workflow(workflow)


@pytest.mark.unit
def test_parse_workflow_missing_edges(db_session):
    """Test parsing fails when 'edges' field is missing"""
    engine = GraphEngine(db_session=db_session)

    workflow = {"nodes": []}

    with pytest.raises(GraphValidationError, match="missing 'edges'"):
        engine._parse_workflow(workflow)


@pytest.mark.unit
def test_parse_workflow_invalid_node(db_session):
    """Test parsing fails with invalid node type"""
    engine = GraphEngine(db_session=db_session)

    workflow = {
        "nodes": [
            {"id": "bad", "type": "unknown_type"}
        ],
        "edges": []
    }

    with pytest.raises(GraphValidationError, match="Failed to parse node"):
        engine._parse_workflow(workflow)


# ============================================================================
# GRAPH VALIDATION TESTS
# ============================================================================

@pytest.mark.unit
def test_validate_graph_valid(simple_workflow, db_session):
    """Test validation passes for valid graph"""
    engine = GraphEngine(db_session=db_session)

    nodes, edges = engine._parse_workflow(simple_workflow)
    engine._validate_graph(nodes, edges)  # Should not raise


@pytest.mark.unit
def test_validate_graph_no_start(invalid_workflow_no_start, db_session):
    """Test validation fails when start node is missing"""
    engine = GraphEngine(db_session=db_session)

    nodes, edges = engine._parse_workflow(invalid_workflow_no_start)

    with pytest.raises(GraphValidationError, match="must have exactly 1 start node"):
        engine._validate_graph(nodes, edges)


@pytest.mark.unit
def test_validate_graph_no_end(invalid_workflow_no_end, db_session):
    """Test validation fails when end node is missing"""
    engine = GraphEngine(db_session=db_session)

    nodes, edges = engine._parse_workflow(invalid_workflow_no_end)

    with pytest.raises(GraphValidationError, match="must have exactly 1 end node"):
        engine._validate_graph(nodes, edges)


@pytest.mark.unit
def test_validate_graph_cycle(invalid_workflow_cycle, db_session):
    """Test validation fails when graph contains a cycle"""
    engine = GraphEngine(db_session=db_session)

    nodes, edges = engine._parse_workflow(invalid_workflow_cycle)

    with pytest.raises(GraphValidationError, match="contains a cycle"):
        engine._validate_graph(nodes, edges)


@pytest.mark.unit
def test_validate_graph_orphan_node(invalid_workflow_orphan_node, db_session):
    """Test validation fails when graph contains orphan nodes"""
    engine = GraphEngine(db_session=db_session)

    nodes, edges = engine._parse_workflow(invalid_workflow_orphan_node)

    with pytest.raises(GraphValidationError, match="unreachable nodes"):
        engine._validate_graph(nodes, edges)


# ============================================================================
# WORKFLOW EXECUTION TESTS
# ============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_simple_workflow(simple_workflow, simple_context, db_session, mock_executor):
    """Test execution of a simple linear workflow"""
    engine = GraphEngine(db_session=db_session)

    # Mock the executor
    with patch('src.core.engine.get_executor', return_value=mock_executor):
        result = await engine.execute_workflow(
            workflow_definition=simple_workflow,
            initial_context=simple_context,
            workflow_id=1
        )

    # Verify result structure
    assert result["status"] == "success"
    assert "final_context" in result
    assert "execution_trace" in result
    assert result["nodes_executed"] == 3  # start, action1, end

    # Verify execution trace
    trace = result["execution_trace"]
    assert len(trace) == 3
    assert trace[0]["node_id"] == "start"
    assert trace[1]["node_id"] == "action1"
    assert trace[2]["node_id"] == "end"

    # Verify all nodes succeeded
    for entry in trace:
        assert entry["status"] == "success"

    # Verify executor was called once (for action1)
    assert mock_executor.execute.call_count == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_workflow_with_decision_true_branch(workflow_with_decision, db_session, mock_executor):
    """Test workflow takes true branch in decision node"""
    engine = GraphEngine(db_session=db_session)

    # Mock executor to return amount > 1000
    async def execute_side_effect(code, context, timeout):
        updated = context.copy()
        if "amount" in code:
            updated['amount'] = 1500  # > 1000, should take true branch
        elif "category" in code:
            updated['category'] = 'high'
        return updated

    mock_executor.execute.side_effect = execute_side_effect

    with patch('src.core.engine.get_executor', return_value=mock_executor):
        result = await engine.execute_workflow(
            workflow_definition=workflow_with_decision,
            initial_context={},
            workflow_id=1
        )

    # Should execute: start → calculate → check_amount → high_amount → end
    assert result["status"] == "success"
    assert result["nodes_executed"] == 5

    # Verify high_amount was executed (not low_amount)
    node_ids = [entry["node_id"] for entry in result["execution_trace"]]
    assert "high_amount" in node_ids
    assert "low_amount" not in node_ids

    # Verify decision was recorded
    decision_entry = next(e for e in result["execution_trace"] if e["node_id"] == "check_amount")
    assert decision_entry["decision_result"] == "true"
    assert decision_entry["path_taken"] == "high_amount"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_workflow_with_decision_false_branch(workflow_with_decision, db_session, mock_executor):
    """Test workflow takes false branch in decision node"""
    engine = GraphEngine(db_session=db_session)

    # Mock executor to return amount < 1000
    async def execute_side_effect(code, context, timeout):
        updated = context.copy()
        if "amount" in code:
            updated['amount'] = 500  # < 1000, should take false branch
        elif "category" in code:
            updated['category'] = 'low'
        return updated

    mock_executor.execute.side_effect = execute_side_effect

    with patch('src.core.engine.get_executor', return_value=mock_executor):
        result = await engine.execute_workflow(
            workflow_definition=workflow_with_decision,
            initial_context={},
            workflow_id=1
        )

    # Should execute: start → calculate → check_amount → low_amount → end
    assert result["status"] == "success"

    # Verify low_amount was executed (not high_amount)
    node_ids = [entry["node_id"] for entry in result["execution_trace"]]
    assert "low_amount" in node_ids
    assert "high_amount" not in node_ids

    # Verify decision was recorded
    decision_entry = next(e for e in result["execution_trace"] if e["node_id"] == "check_amount")
    assert decision_entry["decision_result"] == "false"
    assert decision_entry["path_taken"] == "low_amount"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_workflow_multiple_actions(workflow_with_multiple_actions, db_session, mock_executor):
    """Test workflow with multiple sequential actions"""
    engine = GraphEngine(db_session=db_session)

    # Track which steps were executed
    steps_executed = []

    async def execute_side_effect(code, context, timeout):
        updated = context.copy()
        if "step1" in code:
            updated['step1'] = 'done'
            steps_executed.append(1)
        elif "step2" in code:
            updated['step2'] = 'done'
            steps_executed.append(2)
        elif "step3" in code:
            updated['step3'] = 'done'
            steps_executed.append(3)
        return updated

    mock_executor.execute.side_effect = execute_side_effect

    with patch('src.core.engine.get_executor', return_value=mock_executor):
        result = await engine.execute_workflow(
            workflow_definition=workflow_with_multiple_actions,
            initial_context={},
            workflow_id=1
        )

    # Verify all steps executed in order
    assert result["status"] == "success"
    assert result["nodes_executed"] == 5  # start + 3 actions + end
    assert steps_executed == [1, 2, 3]

    # Verify final context has all steps
    assert result["final_context"]["step1"] == "done"
    assert result["final_context"]["step2"] == "done"
    assert result["final_context"]["step3"] == "done"


# ============================================================================
# CONTEXT MANAGEMENT TESTS
# ============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_context_preserved_between_nodes(simple_workflow, db_session, mock_executor):
    """Test context is preserved and passed between nodes"""
    engine = GraphEngine(db_session=db_session)

    # Mock executor to add data to context
    async def execute_side_effect(code, context, timeout):
        # Verify initial context is present
        assert "initial_data" in context

        updated = context.copy()
        updated['from_action'] = 'added_by_action'
        return updated

    mock_executor.execute.side_effect = execute_side_effect

    initial_context = {"initial_data": "preserved"}

    with patch('src.core.engine.get_executor', return_value=mock_executor):
        result = await engine.execute_workflow(
            workflow_definition=simple_workflow,
            initial_context=initial_context,
            workflow_id=1
        )

    # Verify initial context preserved
    assert result["final_context"]["initial_data"] == "preserved"

    # Verify action added new data
    assert result["final_context"]["from_action"] == "added_by_action"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_complex_context_handling(simple_workflow, complex_context, db_session, mock_executor):
    """Test complex nested context is handled correctly"""
    engine = GraphEngine(db_session=db_session)

    # Mock executor to modify nested context
    async def execute_side_effect(code, context, timeout):
        updated = context.copy()
        # Modify nested structure
        updated['invoice']['processed'] = True
        updated['user']['verified'] = True
        return updated

    mock_executor.execute.side_effect = execute_side_effect

    with patch('src.core.engine.get_executor', return_value=mock_executor):
        result = await engine.execute_workflow(
            workflow_definition=simple_workflow,
            initial_context=complex_context,
            workflow_id=1
        )

    # Verify nested modifications preserved
    assert result["final_context"]["invoice"]["processed"] == True
    assert result["final_context"]["user"]["verified"] == True

    # Verify original nested data preserved
    assert result["final_context"]["user"]["id"] == 123
    assert result["final_context"]["invoice"]["amount"] == 1500.00


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_execution_error_handling(simple_workflow, db_session, mock_executor_with_error):
    """Test workflow handles execution errors gracefully"""
    engine = GraphEngine(db_session=db_session)

    with patch('src.core.engine.get_executor', return_value=mock_executor_with_error):
        result = await engine.execute_workflow(
            workflow_definition=simple_workflow,
            initial_context={},
            workflow_id=1
        )

    # Verify workflow failed
    assert result["status"] == "failed"
    assert "error" in result
    assert "Sandbox error" in result["error"]

    # Verify trace shows where it failed
    trace = result["execution_trace"]
    failed_entry = next(e for e in trace if e["status"] == "failed")
    assert failed_entry["node_id"] == "action1"
    assert "Sandbox error" in failed_entry["error_message"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_timeout_error_handling(simple_workflow, db_session, mock_executor_with_timeout):
    """Test workflow handles timeout errors"""
    engine = GraphEngine(db_session=db_session)

    with patch('src.core.engine.get_executor', return_value=mock_executor_with_timeout):
        result = await engine.execute_workflow(
            workflow_definition=simple_workflow,
            initial_context={},
            workflow_id=1
        )

    # Verify workflow failed with timeout
    assert result["status"] == "failed"
    assert "timeout" in result["error"].lower()


# ============================================================================
# CHAIN OF WORK TESTS
# ============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_chain_of_work_recorded(db_with_workflow, mock_executor):
    """Test Chain of Work is correctly recorded in database"""
    db_session, workflow = db_with_workflow

    engine = GraphEngine(db_session=db_session)

    with patch('src.core.engine.get_executor', return_value=mock_executor):
        result = await engine.execute_workflow(
            workflow_definition=workflow.graph_definition,
            initial_context={"test": "data"},
            workflow_id=workflow.id
        )

    # Verify execution record exists
    execution = db_session.query(Execution).filter(
        Execution.workflow_id == workflow.id
    ).first()

    assert execution is not None
    assert execution.status == "completed"

    # Verify Chain of Work entries
    chain_entries = db_session.query(ChainOfWork).filter(
        ChainOfWork.execution_id == execution.id
    ).order_by(ChainOfWork.id).all()

    assert len(chain_entries) == 3  # start, process, end

    # Verify first entry (start)
    assert chain_entries[0].node_id == "start"
    assert chain_entries[0].node_type == "start"
    assert chain_entries[0].status == "success"

    # Verify second entry (process)
    assert chain_entries[1].node_id == "process"
    assert chain_entries[1].node_type == "action"
    assert chain_entries[1].status == "success"
    assert chain_entries[1].code_executed is not None

    # Verify third entry (end)
    assert chain_entries[2].node_id == "end"
    assert chain_entries[2].node_type == "end"
    assert chain_entries[2].status == "success"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_chain_of_work_records_decision(workflow_with_decision, db_session, mock_executor):
    """Test Chain of Work records decision results"""
    engine = GraphEngine(db_session=db_session)

    # Mock executor to take true branch
    async def execute_side_effect(code, context, timeout):
        updated = context.copy()
        if "amount" in code:
            updated['amount'] = 1500
        elif "category" in code:
            updated['category'] = 'high'
        return updated

    mock_executor.execute.side_effect = execute_side_effect

    # Create execution record manually for testing
    from src.models.execution import Execution
    execution = Execution(workflow_id=1, status="running")
    db_session.add(execution)
    db_session.commit()
    db_session.refresh(execution)

    with patch('src.core.engine.get_executor', return_value=mock_executor):
        result = await engine.execute_workflow(
            workflow_definition=workflow_with_decision,
            initial_context={},
            workflow_id=1
        )

    # Find decision entry in Chain of Work
    decision_entries = db_session.query(ChainOfWork).filter(
        ChainOfWork.execution_id == execution.id,
        ChainOfWork.node_type == "decision"
    ).all()

    assert len(decision_entries) == 1
    decision_entry = decision_entries[0]

    # Verify decision was recorded
    assert decision_entry.node_id == "check_amount"
    assert decision_entry.decision_result == "true"
    assert decision_entry.path_taken == "high_amount"
    assert decision_entry.status == "success"


# ============================================================================
# INTEGRATION-LIKE TESTS (still unit, but more complex)
# ============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_full_workflow_lifecycle(db_with_workflow, mock_executor):
    """Test complete workflow lifecycle: parse → validate → execute → record"""
    db_session, workflow = db_with_workflow

    engine = GraphEngine(db_session=db_session)

    # Execute workflow
    with patch('src.core.engine.get_executor', return_value=mock_executor):
        result = await engine.execute_workflow(
            workflow_definition=workflow.graph_definition,
            initial_context={"user_id": 123},
            workflow_id=workflow.id
        )

    # Verify successful execution
    assert result["status"] == "success"
    assert result["nodes_executed"] == 3

    # Verify database records
    execution = db_session.query(Execution).filter(
        Execution.workflow_id == workflow.id
    ).first()

    assert execution.status == "completed"
    assert execution.result is not None

    # Verify complete Chain of Work
    chain_count = db_session.query(ChainOfWork).filter(
        ChainOfWork.execution_id == execution.id
    ).count()

    assert chain_count == 3
