"""
Pytest fixtures for NOVA tests

This module provides shared fixtures for all tests:
- Database session fixtures
- Mock E2B executor
- Sample workflow definitions
- Test data generators
"""

import pytest
from unittest.mock import Mock, AsyncMock, MagicMock
from typing import Dict, Any
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from src.models import Base
from src.core.executors import ExecutorStrategy


# ============================================================================
# DATABASE FIXTURES
# ============================================================================

@pytest.fixture(scope="function")
def db_session():
    """
    Create an in-memory SQLite database for testing.
    Each test gets a fresh database that's torn down after the test.
    """
    # Create in-memory SQLite engine
    engine = create_engine("sqlite:///:memory:", echo=False)

    # Create all tables
    Base.metadata.create_all(engine)

    # Create session
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture(scope="function")
def db_with_workflow(db_session):
    """
    Database session with a sample workflow pre-loaded.
    """
    from src.models.workflow import Workflow

    workflow = Workflow(
        name="Test Workflow",
        description="A simple test workflow",
        graph_definition={
            "nodes": [
                {"id": "start", "type": "start"},
                {"id": "process", "type": "action", "code": "context['result'] = 42", "executor": "e2b"},
                {"id": "end", "type": "end"}
            ],
            "edges": [
                {"from": "start", "to": "process"},
                {"from": "process", "to": "end"}
            ]
        }
    )

    db_session.add(workflow)
    db_session.commit()
    db_session.refresh(workflow)

    return db_session, workflow


# ============================================================================
# EXECUTOR FIXTURES
# ============================================================================

@pytest.fixture
def mock_executor():
    """
    Mock executor that returns a simple updated context.
    Use this for unit tests that don't need actual E2B execution.
    """
    mock = AsyncMock(spec=ExecutorStrategy)

    # Default behavior: return context with added 'executed' flag
    async def execute_side_effect(code, context, timeout):
        updated = context.copy()
        updated['executed'] = True
        return updated

    mock.execute.side_effect = execute_side_effect

    return mock


@pytest.fixture
def mock_executor_with_error():
    """
    Mock executor that raises an error.
    Use this to test error handling.
    """
    from src.core.exceptions import E2BSandboxError

    mock = AsyncMock(spec=ExecutorStrategy)
    mock.execute.side_effect = E2BSandboxError("Sandbox error", sandbox_id="test-123")

    return mock


@pytest.fixture
def mock_executor_with_timeout():
    """
    Mock executor that raises a timeout error.
    """
    from src.core.exceptions import E2BTimeoutError

    mock = AsyncMock(spec=ExecutorStrategy)
    mock.execute.side_effect = E2BTimeoutError("Execution timeout", timeout_seconds=60)

    return mock


# ============================================================================
# WORKFLOW DEFINITION FIXTURES
# ============================================================================

@pytest.fixture
def simple_workflow():
    """
    Simple linear workflow: Start → Action → End
    """
    return {
        "nodes": [
            {"id": "start", "type": "start"},
            {"id": "action1", "type": "action", "code": "context['value'] = 42", "executor": "e2b"},
            {"id": "end", "type": "end"}
        ],
        "edges": [
            {"from": "start", "to": "action1"},
            {"from": "action1", "to": "end"}
        ]
    }


@pytest.fixture
def workflow_with_decision():
    """
    Workflow with conditional branching:
    Start → Action → Decision → [High/Low] → End
    """
    return {
        "nodes": [
            {"id": "start", "type": "start"},
            {"id": "calculate", "type": "action", "code": "context['amount'] = 1500", "executor": "e2b"},
            {"id": "check_amount", "type": "decision", "condition": "context.get('amount', 0) > 1000"},
            {"id": "high_amount", "type": "action", "code": "context['category'] = 'high'", "executor": "e2b"},
            {"id": "low_amount", "type": "action", "code": "context['category'] = 'low'", "executor": "e2b"},
            {"id": "end", "type": "end"}
        ],
        "edges": [
            {"from": "start", "to": "calculate"},
            {"from": "calculate", "to": "check_amount"},
            {"from": "check_amount", "to": "high_amount", "condition": "true"},
            {"from": "check_amount", "to": "low_amount", "condition": "false"},
            {"from": "high_amount", "to": "end"},
            {"from": "low_amount", "to": "end"}
        ]
    }


@pytest.fixture
def workflow_with_multiple_actions():
    """
    Workflow with multiple sequential actions:
    Start → Action1 → Action2 → Action3 → End
    """
    return {
        "nodes": [
            {"id": "start", "type": "start"},
            {"id": "action1", "type": "action", "code": "context['step1'] = 'done'", "executor": "e2b"},
            {"id": "action2", "type": "action", "code": "context['step2'] = 'done'", "executor": "e2b"},
            {"id": "action3", "type": "action", "code": "context['step3'] = 'done'", "executor": "e2b"},
            {"id": "end", "type": "end"}
        ],
        "edges": [
            {"from": "start", "to": "action1"},
            {"from": "action1", "to": "action2"},
            {"from": "action2", "to": "action3"},
            {"from": "action3", "to": "end"}
        ]
    }


@pytest.fixture
def invalid_workflow_no_start():
    """
    Invalid workflow: missing start node
    """
    return {
        "nodes": [
            {"id": "action1", "type": "action", "code": "x=1", "executor": "e2b"},
            {"id": "end", "type": "end"}
        ],
        "edges": [
            {"from": "action1", "to": "end"}
        ]
    }


@pytest.fixture
def invalid_workflow_no_end():
    """
    Invalid workflow: missing end node
    """
    return {
        "nodes": [
            {"id": "start", "type": "start"},
            {"id": "action1", "type": "action", "code": "x=1", "executor": "e2b"}
        ],
        "edges": [
            {"from": "start", "to": "action1"}
        ]
    }


@pytest.fixture
def invalid_workflow_cycle():
    """
    Invalid workflow: contains a cycle
    """
    return {
        "nodes": [
            {"id": "start", "type": "start"},
            {"id": "action1", "type": "action", "code": "x=1", "executor": "e2b"},
            {"id": "action2", "type": "action", "code": "x=2", "executor": "e2b"},
            {"id": "end", "type": "end"}
        ],
        "edges": [
            {"from": "start", "to": "action1"},
            {"from": "action1", "to": "action2"},
            {"from": "action2", "to": "action1"},  # Cycle!
            {"from": "action2", "to": "end"}
        ]
    }


@pytest.fixture
def invalid_workflow_orphan_node():
    """
    Invalid workflow: contains orphan node (not reachable from start)
    """
    return {
        "nodes": [
            {"id": "start", "type": "start"},
            {"id": "action1", "type": "action", "code": "x=1", "executor": "e2b"},
            {"id": "orphan", "type": "action", "code": "x=2", "executor": "e2b"},  # Orphan!
            {"id": "end", "type": "end"}
        ],
        "edges": [
            {"from": "start", "to": "action1"},
            {"from": "action1", "to": "end"}
            # orphan node has no edges connecting it
        ]
    }


# ============================================================================
# CONTEXT FIXTURES
# ============================================================================

@pytest.fixture
def simple_context():
    """
    Simple context for testing
    """
    return {
        "user_id": 123,
        "email": "test@example.com",
        "timestamp": "2025-10-31T12:00:00Z"
    }


@pytest.fixture
def complex_context():
    """
    Complex context with nested data
    """
    return {
        "user": {
            "id": 123,
            "name": "Test User",
            "email": "test@example.com"
        },
        "invoice": {
            "id": 456,
            "amount": 1500.00,
            "currency": "EUR",
            "items": [
                {"name": "Item 1", "price": 500.00},
                {"name": "Item 2", "price": 1000.00}
            ]
        },
        "metadata": {
            "timestamp": "2025-10-31T12:00:00Z",
            "source": "email"
        }
    }


# ============================================================================
# UTILITY FIXTURES
# ============================================================================

@pytest.fixture
def capture_logs(caplog):
    """
    Fixture to capture logs for testing
    """
    import logging
    caplog.set_level(logging.DEBUG)
    return caplog
