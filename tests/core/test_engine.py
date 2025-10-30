"""
Tests for GraphEngine

Tests cover:
- Workflow parsing
- Graph validation (start/end nodes, edges)
- Node execution flow
- Decision branching
- Context management between nodes
- Error handling
- Execution trace
"""

import pytest
from unittest.mock import AsyncMock, patch, Mock

from src.core.engine import (
    GraphEngine,
    GraphValidationError,
    GraphExecutionError
)


# =============================================================================
# Workflow Parsing Tests
# =============================================================================


def test_parse_workflow_valid():
    """Test parsing a valid workflow"""
    engine = GraphEngine(sandbox_url="http://test.com")

    workflow = {
        "nodes": [
            {"id": "start", "type": "start"},
            {"id": "end", "type": "end"}
        ],
        "edges": [
            {"from": "start", "to": "end"}
        ]
    }

    nodes, edges = engine._parse_workflow(workflow)

    assert len(nodes) == 2
    assert "start" in nodes
    assert "end" in nodes
    assert len(edges) == 1


def test_parse_workflow_missing_nodes():
    """Test parsing fails when 'nodes' field is missing"""
    engine = GraphEngine(sandbox_url="http://test.com")

    workflow = {"edges": []}

    with pytest.raises(GraphValidationError, match="missing 'nodes'"):
        engine._parse_workflow(workflow)


def test_parse_workflow_missing_edges():
    """Test parsing fails when 'edges' field is missing"""
    engine = GraphEngine(sandbox_url="http://test.com")

    workflow = {"nodes": []}

    with pytest.raises(GraphValidationError, match="missing 'edges'"):
        engine._parse_workflow(workflow)


def test_parse_workflow_invalid_node():
    """Test parsing fails with invalid node data"""
    engine = GraphEngine(sandbox_url="http://test.com")

    workflow = {
        "nodes": [
            {"id": "bad", "type": "unknown_type"}
        ],
        "edges": []
    }

    with pytest.raises(GraphValidationError, match="Failed to parse node"):
        engine._parse_workflow(workflow)


# =============================================================================
# Graph Validation Tests
# =============================================================================


def test_validate_graph_valid():
    """Test validation passes for valid graph"""
    engine = GraphEngine(sandbox_url="http://test.com")

    workflow = {
        "nodes": [
            {"id": "start", "type": "start"},
            {"id": "process", "type": "action", "code": "x=1"},
            {"id": "end", "type": "end"}
        ],
        "edges": [
            {"from": "start", "to": "process"},
            {"from": "process", "to": "end"}
        ]
    }

    nodes, edges = engine._parse_workflow(workflow)
    engine._validate_graph(nodes, edges)  # Should not raise


def test_validate_graph_no_start():
    """Test validation fails without StartNode"""
    engine = GraphEngine(sandbox_url="http://test.com")

    workflow = {
        "nodes": [
            {"id": "process", "type": "action", "code": "x=1"},
            {"id": "end", "type": "end"}
        ],
        "edges": []
    }

    nodes, edges = engine._parse_workflow(workflow)

    with pytest.raises(GraphValidationError, match="exactly one StartNode"):
        engine._validate_graph(nodes, edges)


def test_validate_graph_multiple_starts():
    """Test validation fails with multiple StartNodes"""
    engine = GraphEngine(sandbox_url="http://test.com")

    workflow = {
        "nodes": [
            {"id": "start1", "type": "start"},
            {"id": "start2", "type": "start"},
            {"id": "end", "type": "end"}
        ],
        "edges": []
    }

    nodes, edges = engine._parse_workflow(workflow)

    with pytest.raises(GraphValidationError, match="exactly one StartNode"):
        engine._validate_graph(nodes, edges)


def test_validate_graph_no_end():
    """Test validation fails without EndNode"""
    engine = GraphEngine(sandbox_url="http://test.com")

    workflow = {
        "nodes": [
            {"id": "start", "type": "start"},
            {"id": "process", "type": "action", "code": "x=1"}
        ],
        "edges": []
    }

    nodes, edges = engine._parse_workflow(workflow)

    with pytest.raises(GraphValidationError, match="at least one EndNode"):
        engine._validate_graph(nodes, edges)


def test_validate_graph_edge_to_nonexistent_node():
    """Test validation fails when edge references non-existent node"""
    engine = GraphEngine(sandbox_url="http://test.com")

    workflow = {
        "nodes": [
            {"id": "start", "type": "start"},
            {"id": "end", "type": "end"}
        ],
        "edges": [
            {"from": "start", "to": "nonexistent"}
        ]
    }

    nodes, edges = engine._parse_workflow(workflow)

    with pytest.raises(GraphValidationError, match="non-existent node"):
        engine._validate_graph(nodes, edges)


# =============================================================================
# Next Node Finding Tests
# =============================================================================


def test_find_next_node_single_edge():
    """Test finding next node with single outgoing edge"""
    engine = GraphEngine(sandbox_url="http://test.com")

    edges = [
        {"from": "start", "to": "process"},
        {"from": "process", "to": "end"}
    ]

    from src.core.context import ContextManager
    context = ContextManager()

    next_node = engine._find_next_node("start", edges, context)
    assert next_node == "process"


def test_find_next_node_no_edges():
    """Test finding next node when no outgoing edges (EndNode)"""
    engine = GraphEngine(sandbox_url="http://test.com")

    edges = [
        {"from": "start", "to": "end"}
    ]

    from src.core.context import ContextManager
    context = ContextManager()

    next_node = engine._find_next_node("end", edges, context)
    assert next_node is None


def test_find_next_node_decision_true():
    """Test decision branching with true condition"""
    engine = GraphEngine(sandbox_url="http://test.com")

    edges = [
        {"from": "decide", "to": "true_path", "condition": "true"},
        {"from": "decide", "to": "false_path", "condition": "false"}
    ]

    from src.core.context import ContextManager
    context = ContextManager()
    context.set("branch_decision", True)

    next_node = engine._find_next_node("decide", edges, context)
    assert next_node == "true_path"


def test_find_next_node_decision_false():
    """Test decision branching with false condition"""
    engine = GraphEngine(sandbox_url="http://test.com")

    edges = [
        {"from": "decide", "to": "true_path", "condition": "true"},
        {"from": "decide", "to": "false_path", "condition": "false"}
    ]

    from src.core.context import ContextManager
    context = ContextManager()
    context.set("branch_decision", False)

    next_node = engine._find_next_node("decide", edges, context)
    assert next_node == "false_path"


def test_find_next_node_decision_missing():
    """Test error when decision result is missing in context"""
    engine = GraphEngine(sandbox_url="http://test.com")

    edges = [
        {"from": "decide", "to": "true_path", "condition": "true"},
        {"from": "decide", "to": "false_path", "condition": "false"}
    ]

    from src.core.context import ContextManager
    context = ContextManager()
    # No branch_decision set

    with pytest.raises(GraphExecutionError, match="did not set 'branch_decision'"):
        engine._find_next_node("decide", edges, context)


# =============================================================================
# Workflow Execution Tests (Mocked Sandbox)
# =============================================================================


@pytest.mark.asyncio
async def test_execute_workflow_simple():
    """Test executing a simple linear workflow"""
    engine = GraphEngine(sandbox_url="http://test.com")

    workflow = {
        "nodes": [
            {"id": "start", "type": "start"},
            {"id": "process", "type": "action", "code": "result = 42", "executor": "static"},
            {"id": "end", "type": "end"}
        ],
        "edges": [
            {"from": "start", "to": "process"},
            {"from": "process", "to": "end"}
        ]
    }

    # Mock executor
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "status": "success",
        "output": '{"result": 42}'
    }

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)

        result = await engine.execute_workflow(workflow, initial_context={})

    assert result["status"] == "success"
    assert result["final_context"]["result"] == 42
    assert len(result["execution_trace"]) == 3  # start, process, end
    assert result["nodes_executed"] == 3


@pytest.mark.asyncio
async def test_execute_workflow_with_decision():
    """Test executing workflow with decision branching (simplified)"""
    engine = GraphEngine(sandbox_url="http://test.com")

    workflow = {
        "nodes": [
            {"id": "start", "type": "start"},
            {"id": "decide", "type": "decision", "code": "context['branch_decision'] = True"},
            {"id": "true_end", "type": "end"},
            {"id": "false_end", "type": "end"}
        ],
        "edges": [
            {"from": "start", "to": "decide"},
            {"from": "decide", "to": "true_end", "condition": "true"},
            {"from": "decide", "to": "false_end", "condition": "false"}
        ]
    }

    # Mock executor - decision node sets branch_decision = True
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "status": "success",
        "output": '{"branch_decision": true}'
    }

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)

        result = await engine.execute_workflow(workflow, initial_context={})

    assert result["status"] == "success"
    assert result["final_context"]["branch_decision"] is True
    # Should have followed true path: start -> decide -> true_end
    assert len(result["execution_trace"]) == 3
    assert result["execution_trace"][-1]["node_id"] == "true_end"


@pytest.mark.asyncio
async def test_execute_workflow_with_initial_context():
    """Test workflow execution with initial context"""
    engine = GraphEngine(sandbox_url="http://test.com")

    workflow = {
        "nodes": [
            {"id": "start", "type": "start"},
            {"id": "process", "type": "action", "code": "doubled = value * 2", "executor": "static"},
            {"id": "end", "type": "end"}
        ],
        "edges": [
            {"from": "start", "to": "process"},
            {"from": "process", "to": "end"}
        ]
    }

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "status": "success",
        "output": '{"value": 10, "doubled": 20}'
    }

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)

        result = await engine.execute_workflow(workflow, initial_context={"value": 10})

    assert result["status"] == "success"
    assert result["final_context"]["value"] == 10
    assert result["final_context"]["doubled"] == 20


@pytest.mark.asyncio
async def test_execute_workflow_node_failure():
    """Test workflow handles node execution failure"""
    engine = GraphEngine(sandbox_url="http://test.com")

    workflow = {
        "nodes": [
            {"id": "start", "type": "start"},
            {"id": "failing_node", "type": "action", "code": "raise Exception('error')", "executor": "static"},
            {"id": "end", "type": "end"}
        ],
        "edges": [
            {"from": "start", "to": "failing_node"},
            {"from": "failing_node", "to": "end"}
        ]
    }

    # Mock failing response
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "status": "error",
        "error": "NameError: execution failed"
    }

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)

        result = await engine.execute_workflow(workflow, initial_context={})

    assert result["status"] == "failed"
    assert "failed_at_node" in result
    assert result["failed_at_node"] == "failing_node"


# =============================================================================
# Execution Trace Tests
# =============================================================================


@pytest.mark.asyncio
async def test_execution_trace_captures_metadata():
    """Test that execution trace captures all node metadata"""
    engine = GraphEngine(sandbox_url="http://test.com")

    workflow = {
        "nodes": [
            {"id": "start", "type": "start"},
            {"id": "process", "type": "action", "code": "x = 1", "executor": "static"},
            {"id": "end", "type": "end"}
        ],
        "edges": [
            {"from": "start", "to": "process"},
            {"from": "process", "to": "end"}
        ]
    }

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "status": "success",
        "output": '{"x": 1}'
    }

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)

        result = await engine.execute_workflow(workflow, initial_context={})

    trace = result["execution_trace"]

    # Check start node
    assert trace[0]["node_id"] == "start"
    assert trace[0]["node_type"] == "start"
    assert "execution_time" in trace[0]
    assert "input_context" in trace[0]
    assert "output_result" in trace[0]

    # Check action node
    assert trace[1]["node_id"] == "process"
    assert trace[1]["code_executed"] == "x = 1"

    # Check end node
    assert trace[2]["node_id"] == "end"


@pytest.mark.asyncio
async def test_execution_trace_decision_metadata():
    """Test that decision nodes record decision result and path taken"""
    engine = GraphEngine(sandbox_url="http://test.com")

    workflow = {
        "nodes": [
            {"id": "start", "type": "start"},
            {"id": "decide", "type": "decision", "code": "context['branch_decision'] = False"},
            {"id": "true_node", "type": "end"},
            {"id": "false_node", "type": "end"}
        ],
        "edges": [
            {"from": "start", "to": "decide"},
            {"from": "decide", "to": "true_node", "condition": "true"},
            {"from": "decide", "to": "false_node", "condition": "false"}
        ]
    }

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "status": "success",
        "output": '{"branch_decision": false}'
    }

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)

        result = await engine.execute_workflow(workflow, initial_context={})

    trace = result["execution_trace"]
    decision_trace = trace[1]  # decide node

    assert decision_trace["node_id"] == "decide"
    assert decision_trace["decision_result"] == "false"
    assert decision_trace["path_taken"] == "false_node"
