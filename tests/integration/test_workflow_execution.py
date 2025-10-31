"""
Integration Tests for Workflow Execution

These tests verify complete workflow execution flows:
- Invoice Processing workflow (high/low budget paths)
- Database persistence (Execution + Chain of Work)
- Error handling and recovery
- Context propagation
"""

import pytest
from unittest.mock import patch, AsyncMock

from src.core.engine import GraphEngine
from src.models.workflow import Workflow
from src.models.execution import Execution
from src.models.chain_of_work import ChainOfWork


# ============================================================================
# INVOICE PROCESSING WORKFLOW TESTS
# ============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_invoice_processing_high_budget(db_session):
    """
    Test Invoice Processing workflow with high budget (>1000 EUR).

    Flow: Start → Extract → Validate → Check → High Budget Path → End
    """
    # Create Invoice Processing workflow
    workflow = Workflow(
        name="Invoice Processing Integration Test",
        description="Test high budget path",
        graph_definition={
            "nodes": [
                {"id": "start", "type": "start"},
                {"id": "extract", "type": "action", "code": """
# Simulate email extraction
context['has_emails'] = True
context['email_from'] = 'test@example.com'
context['passes_whitelist'] = True
context['has_pdf'] = True
context['pdf_filename'] = 'invoice.pdf'
""", "executor": "e2b"},
                {"id": "validate", "type": "action", "code": """
# Simulate OCR and amount extraction
context['ocr_text'] = 'Invoice Total: 1500 EUR'
context['total_amount'] = 1500.0
""", "executor": "e2b"},
                {"id": "check_budget", "type": "decision", "code": """
# Check if total amount exceeds budget threshold
context['branch_decision'] = context.get('total_amount', 0) > 1000
"""},
                {"id": "high_budget", "type": "action", "code": """
# High budget notification
context['budget_category'] = 'high'
context['requires_approval'] = True
context['notification_sent'] = True
""", "executor": "e2b"},
                {"id": "low_budget", "type": "action", "code": """
# Low budget auto-approval
context['budget_category'] = 'low'
context['requires_approval'] = False
context['auto_approved'] = True
""", "executor": "e2b"},
                {"id": "end", "type": "end"}
            ],
            "edges": [
                {"from": "start", "to": "extract"},
                {"from": "extract", "to": "validate"},
                {"from": "validate", "to": "check_budget"},
                {"from": "check_budget", "to": "high_budget", "condition": "true"},
                {"from": "check_budget", "to": "low_budget", "condition": "false"},
                {"from": "high_budget", "to": "end"},
                {"from": "low_budget", "to": "end"}
            ]
        }
    )

    db_session.add(workflow)
    db_session.commit()
    db_session.refresh(workflow)

    # Mock E2B executor to execute code realistically
    mock_executor = AsyncMock()

    async def execute_code(code, context, timeout):
        # Execute code in local context
        local_context = context.copy()
        exec(code, {"context": local_context})
        return local_context

    mock_executor.execute.side_effect = execute_code

    # Execute workflow
    engine = GraphEngine(db_session=db_session)

    with patch('src.core.engine.get_executor', return_value=mock_executor):
        result = await engine.execute_workflow(
            workflow_definition=workflow.graph_definition,
            initial_context={
                "client_slug": "test-client",
                "invoice_url": "https://example.com/invoice.pdf"
            },
            workflow_id=workflow.id
        )

    # Verify execution completed successfully
    assert result["status"] == "success"
    assert result["nodes_executed"] == 6  # start, extract, validate, check, high_budget, end

    # Verify correct path taken
    node_ids = [entry["node_id"] for entry in result["execution_trace"]]
    assert "high_budget" in node_ids
    assert "low_budget" not in node_ids

    # Verify final context has expected data
    final_context = result["final_context"]
    assert final_context["total_amount"] == 1500.0
    assert final_context["budget_category"] == "high"
    assert final_context["requires_approval"] == True
    assert final_context["notification_sent"] == True

    # Verify database records
    execution = db_session.query(Execution).filter(
        Execution.workflow_id == workflow.id
    ).first()

    assert execution is not None
    assert execution.status == "completed"
    assert execution.result is not None

    # Verify Chain of Work
    chain_entries = db_session.query(ChainOfWork).filter(
        ChainOfWork.execution_id == execution.id
    ).order_by(ChainOfWork.id).all()

    assert len(chain_entries) == 6

    # Verify decision node recorded correctly
    decision_entry = next(e for e in chain_entries if e.node_id == "check_budget")
    assert decision_entry.decision_result == "true"
    assert decision_entry.path_taken == "high_budget"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_invoice_processing_low_budget(db_session):
    """
    Test Invoice Processing workflow with low budget (≤1000 EUR).

    Flow: Start → Extract → Validate → Check → Low Budget Path → End
    """
    workflow = Workflow(
        name="Invoice Processing Low Budget Test",
        description="Test low budget path",
        graph_definition={
            "nodes": [
                {"id": "start", "type": "start"},
                {"id": "extract", "type": "action", "code": """
context['has_emails'] = True
context['email_from'] = 'test@example.com'
context['passes_whitelist'] = True
context['has_pdf'] = True
""", "executor": "e2b"},
                {"id": "validate", "type": "action", "code": """
context['ocr_text'] = 'Invoice Total: 500 EUR'
context['total_amount'] = 500.0
""", "executor": "e2b"},
                {"id": "check_budget", "type": "decision", "code": """
# Check if total amount exceeds budget threshold
context['branch_decision'] = context.get('total_amount', 0) > 1000
"""},
                {"id": "high_budget", "type": "action", "code": """
context['budget_category'] = 'high'
context['requires_approval'] = True
""", "executor": "e2b"},
                {"id": "low_budget", "type": "action", "code": """
context['budget_category'] = 'low'
context['requires_approval'] = False
context['auto_approved'] = True
""", "executor": "e2b"},
                {"id": "end", "type": "end"}
            ],
            "edges": [
                {"from": "start", "to": "extract"},
                {"from": "extract", "to": "validate"},
                {"from": "validate", "to": "check_budget"},
                {"from": "check_budget", "to": "high_budget", "condition": "true"},
                {"from": "check_budget", "to": "low_budget", "condition": "false"},
                {"from": "high_budget", "to": "end"},
                {"from": "low_budget", "to": "end"}
            ]
        }
    )

    db_session.add(workflow)
    db_session.commit()
    db_session.refresh(workflow)

    # Mock executor
    mock_executor = AsyncMock()

    async def execute_code(code, context, timeout):
        local_context = context.copy()
        exec(code, {"context": local_context})
        return local_context

    mock_executor.execute.side_effect = execute_code

    engine = GraphEngine(db_session=db_session)

    with patch('src.core.engine.get_executor', return_value=mock_executor):
        result = await engine.execute_workflow(
            workflow_definition=workflow.graph_definition,
            initial_context={"client_slug": "test-client"},
            workflow_id=workflow.id
        )

    # Verify low budget path taken
    assert result["status"] == "success"

    node_ids = [entry["node_id"] for entry in result["execution_trace"]]
    assert "low_budget" in node_ids
    assert "high_budget" not in node_ids

    # Verify final context
    final_context = result["final_context"]
    assert final_context["total_amount"] == 500.0
    assert final_context["budget_category"] == "low"
    assert final_context["requires_approval"] == False
    assert final_context["auto_approved"] == True

    # Verify decision was recorded
    execution = db_session.query(Execution).filter(
        Execution.workflow_id == workflow.id
    ).first()

    chain_entries = db_session.query(ChainOfWork).filter(
        ChainOfWork.execution_id == execution.id
    ).all()

    decision_entry = next(e for e in chain_entries if e.node_id == "check_budget")
    assert decision_entry.decision_result == "false"
    assert decision_entry.path_taken == "low_budget"


# ============================================================================
# ERROR HANDLING INTEGRATION TESTS
# ============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_workflow_execution_with_node_failure(db_session):
    """
    Test workflow handles node execution failure gracefully.
    Verifies Chain of Work records the failure.
    """
    workflow = Workflow(
        name="Workflow with Failure Test",
        description="Test error handling",
        graph_definition={
            "nodes": [
                {"id": "start", "type": "start"},
                {"id": "step1", "type": "action", "code": "context['step1'] = 'done'", "executor": "e2b"},
                {"id": "failing_step", "type": "action", "code": "context['failing'] = 'will_fail'", "executor": "e2b"},
                {"id": "step3", "type": "action", "code": "context['step3'] = 'done'", "executor": "e2b"},
                {"id": "end", "type": "end"}
            ],
            "edges": [
                {"from": "start", "to": "step1"},
                {"from": "step1", "to": "failing_step"},
                {"from": "failing_step", "to": "step3"},
                {"from": "step3", "to": "end"}
            ]
        }
    )

    db_session.add(workflow)
    db_session.commit()
    db_session.refresh(workflow)

    # Mock executor that fails on failing_step
    from src.core.exceptions import E2BSandboxError

    mock_executor = AsyncMock()

    async def execute_with_failure(code, context, timeout):
        if "failing" in code:
            raise E2BSandboxError("Simulated sandbox error", sandbox_id="test-123")

        # Normal execution
        local_context = context.copy()
        exec(code, {"context": local_context})
        return local_context

    mock_executor.execute.side_effect = execute_with_failure

    engine = GraphEngine(db_session=db_session)

    with patch('src.core.engine.get_executor', return_value=mock_executor):
        result = await engine.execute_workflow(
            workflow_definition=workflow.graph_definition,
            initial_context={},
            workflow_id=workflow.id
        )

    # Verify workflow failed
    assert result["status"] == "failed"
    assert "error" in result
    assert "Simulated sandbox error" in result["error"]

    # Verify partial execution recorded
    trace = result["execution_trace"]

    # Should have: start (success), step1 (success), failing_step (failed)
    assert trace[0]["node_id"] == "start"
    assert trace[0]["status"] == "success"

    assert trace[1]["node_id"] == "step1"
    assert trace[1]["status"] == "success"

    assert trace[2]["node_id"] == "failing_step"
    assert trace[2]["status"] == "failed"
    assert "Simulated sandbox error" in trace[2]["error_message"]

    # step3 should NOT be executed
    node_ids = [entry["node_id"] for entry in trace]
    assert "step3" not in node_ids

    # Verify database records failure
    execution = db_session.query(Execution).filter(
        Execution.workflow_id == workflow.id
    ).first()

    assert execution.status == "failed"
    assert execution.error is not None

    # Verify Chain of Work recorded partial execution
    chain_entries = db_session.query(ChainOfWork).filter(
        ChainOfWork.execution_id == execution.id
    ).all()

    assert len(chain_entries) == 3  # start, step1, failing_step

    failed_entry = next(e for e in chain_entries if e.node_id == "failing_step")
    assert failed_entry.status == "failed"
    assert "Simulated sandbox error" in failed_entry.error_message


# ============================================================================
# CONTEXT PROPAGATION TESTS
# ============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_complex_context_propagation(db_session):
    """
    Test complex nested context is properly propagated through workflow.
    """
    workflow = Workflow(
        name="Complex Context Test",
        description="Test context propagation",
        graph_definition={
            "nodes": [
                {"id": "start", "type": "start"},
                {"id": "add_user", "type": "action", "code": """
context['user'] = {
    'id': 123,
    'name': 'Test User',
    'email': 'test@example.com'
}
""", "executor": "e2b"},
                {"id": "add_invoice", "type": "action", "code": """
context['invoice'] = {
    'id': 456,
    'amount': 1500.00,
    'items': [
        {'name': 'Item 1', 'price': 500.00},
        {'name': 'Item 2', 'price': 1000.00}
    ]
}
""", "executor": "e2b"},
                {"id": "process", "type": "action", "code": """
# Verify nested context is accessible
assert context['user']['id'] == 123
assert context['invoice']['amount'] == 1500.00
assert len(context['invoice']['items']) == 2

# Add processing result
context['processed'] = True
context['total_items'] = len(context['invoice']['items'])
""", "executor": "e2b"},
                {"id": "end", "type": "end"}
            ],
            "edges": [
                {"from": "start", "to": "add_user"},
                {"from": "add_user", "to": "add_invoice"},
                {"from": "add_invoice", "to": "process"},
                {"from": "process", "to": "end"}
            ]
        }
    )

    db_session.add(workflow)
    db_session.commit()
    db_session.refresh(workflow)

    # Mock executor
    mock_executor = AsyncMock()

    async def execute_code(code, context, timeout):
        local_context = context.copy()
        exec(code, {"context": local_context})
        return local_context

    mock_executor.execute.side_effect = execute_code

    engine = GraphEngine(db_session=db_session)

    with patch('src.core.engine.get_executor', return_value=mock_executor):
        result = await engine.execute_workflow(
            workflow_definition=workflow.graph_definition,
            initial_context={"initial_data": "preserved"},
            workflow_id=workflow.id
        )

    # Verify success
    assert result["status"] == "success"

    # Verify nested context preserved
    final_context = result["final_context"]

    assert final_context["initial_data"] == "preserved"  # Initial context preserved
    assert final_context["user"]["id"] == 123
    assert final_context["user"]["name"] == "Test User"
    assert final_context["invoice"]["amount"] == 1500.00
    assert len(final_context["invoice"]["items"]) == 2
    assert final_context["processed"] == True
    assert final_context["total_items"] == 2


# ============================================================================
# MULTI-STEP SEQUENTIAL WORKFLOW TESTS
# ============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_multi_step_sequential_workflow(db_session):
    """
    Test workflow with many sequential steps maintains state correctly.
    """
    # Create workflow with 10 sequential steps
    nodes = [{"id": "start", "type": "start"}]
    edges = []

    for i in range(1, 11):
        nodes.append({
            "id": f"step{i}",
            "type": "action",
            "code": f"context['step{i}'] = {i}",
            "executor": "e2b"
        })

        if i == 1:
            edges.append({"from": "start", "to": "step1"})
        else:
            edges.append({"from": f"step{i-1}", "to": f"step{i}"})

    nodes.append({"id": "end", "type": "end"})
    edges.append({"from": "step10", "to": "end"})

    workflow = Workflow(
        name="Multi-Step Sequential Test",
        description="Test 10 sequential steps",
        graph_definition={"nodes": nodes, "edges": edges}
    )

    db_session.add(workflow)
    db_session.commit()
    db_session.refresh(workflow)

    # Mock executor
    mock_executor = AsyncMock()

    async def execute_code(code, context, timeout):
        local_context = context.copy()
        exec(code, {"context": local_context})
        return local_context

    mock_executor.execute.side_effect = execute_code

    engine = GraphEngine(db_session=db_session)

    with patch('src.core.engine.get_executor', return_value=mock_executor):
        result = await engine.execute_workflow(
            workflow_definition=workflow.graph_definition,
            initial_context={},
            workflow_id=workflow.id
        )

    # Verify all steps executed
    assert result["status"] == "success"
    assert result["nodes_executed"] == 12  # start + 10 steps + end

    # Verify final context has all step data
    final_context = result["final_context"]
    for i in range(1, 11):
        assert final_context[f"step{i}"] == i

    # Verify Chain of Work has all entries
    execution = db_session.query(Execution).filter(
        Execution.workflow_id == workflow.id
    ).first()

    chain_entries = db_session.query(ChainOfWork).filter(
        ChainOfWork.execution_id == execution.id
    ).all()

    assert len(chain_entries) == 12

    # Verify steps executed in order
    step_nodes = [e for e in chain_entries if e.node_type == "action"]
    assert len(step_nodes) == 10

    for i, entry in enumerate(step_nodes, 1):
        assert entry.node_id == f"step{i}"
        assert entry.status == "success"
