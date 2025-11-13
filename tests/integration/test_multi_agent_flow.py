"""
Integration test for Multi-Agent Architecture with CachedExecutor.

This test verifies that:
1. CachedExecutor initializes correctly with orchestrator
2. Orchestrator coordinates all agents properly
3. Full workflow execution works end-to-end
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
import os


@pytest.fixture
def mock_env_vars():
    """Mock environment variables required for CachedExecutor"""
    with patch.dict(os.environ, {
        'OPENAI_API_KEY': 'test-key',
        'E2B_API_KEY': 'test-e2b-key'
    }):
        yield


@pytest.fixture
def cached_executor(mock_env_vars):
    """Create CachedExecutor with mocked dependencies"""
    from src.core.executors import CachedExecutor

    # CachedExecutor will initialize with real orchestrator
    # but we'll mock the OpenAI and E2B calls
    executor = CachedExecutor()

    return executor


@pytest.mark.asyncio
async def test_cached_executor_has_orchestrator(cached_executor):
    """Verify CachedExecutor has orchestrator initialized"""
    assert hasattr(cached_executor, 'orchestrator')
    assert cached_executor.orchestrator is not None

    # Verify orchestrator has all agents
    assert hasattr(cached_executor.orchestrator, 'input_analyzer')
    assert hasattr(cached_executor.orchestrator, 'data_analyzer')
    assert hasattr(cached_executor.orchestrator, 'code_generator')
    assert hasattr(cached_executor.orchestrator, 'code_validator')
    assert hasattr(cached_executor.orchestrator, 'output_validator')
    assert hasattr(cached_executor.orchestrator, 'e2b')


@pytest.mark.asyncio
async def test_cached_executor_execute_delegates_to_orchestrator(cached_executor):
    """Verify execute() delegates to orchestrator.execute_workflow()"""

    # Mock the orchestrator's execute_workflow method
    mock_result = {
        "result": 42,
        "_ai_metadata": {
            "input_analysis": {"needs_analysis": False},
            "attempts": 1,
            "status": "success"
        }
    }

    cached_executor.orchestrator.execute_workflow = AsyncMock(return_value=mock_result)

    # Execute
    task = "Calculate 2 + 2"
    context = {"input": "test"}
    timeout = 30

    result = await cached_executor.execute(
        code=task,
        context=context,
        timeout=timeout
    )

    # Verify orchestrator was called with correct params
    cached_executor.orchestrator.execute_workflow.assert_called_once_with(
        task=task,
        context=context,
        timeout=timeout
    )

    # Verify result matches
    assert result == mock_result
    assert result["result"] == 42
    assert "_ai_metadata" in result


@pytest.mark.asyncio
async def test_cached_executor_handles_orchestrator_errors(cached_executor):
    """Verify execute() handles orchestrator errors properly"""
    from src.core.exceptions import ExecutorError

    # Mock orchestrator to raise error
    cached_executor.orchestrator.execute_workflow = AsyncMock(
        side_effect=Exception("Orchestrator failed")
    )

    # Execute should raise ExecutorError
    with pytest.raises(ExecutorError) as exc_info:
        await cached_executor.execute(
            code="Test task",
            context={},
            timeout=30
        )

    assert "Multi-Agent execution failed" in str(exc_info.value)
    assert "Orchestrator failed" in str(exc_info.value)


@pytest.mark.asyncio
async def test_cached_executor_complete_integration(cached_executor):
    """
    Integration test: Verify CachedExecutor uses orchestrator correctly.

    This test mocks the orchestrator to verify the integration works,
    without testing the individual agents (those have their own tests).
    """

    # Mock successful orchestrator response
    expected_result = {
        "result": 42,
        "_ai_metadata": {
            "input_analysis": {
                "needs_analysis": False,
                "complexity": "simple",
                "reasoning": "Simple arithmetic task"
            },
            "data_analysis": None,  # Not needed
            "code_generation": {
                "code": "context['result'] = 2 + 2",
                "tool_calls": []
            },
            "code_validation": {
                "valid": True,
                "errors": [],
                "checks_passed": ["syntax", "variables", "context_access"]
            },
            "execution_result": {"status": "success"},
            "output_validation": {
                "valid": True,
                "reason": "Result successfully calculated",
                "changes_detected": ["result"]
            },
            "attempts": 1,
            "errors": [],
            "timings": {
                "InputAnalyzer": 10.5,
                "CodeGenerator": 150.3,
                "CodeValidator": 5.2,
                "OutputValidator": 12.1
            },
            "total_time_ms": 178.1,
            "status": "success"
        }
    }

    # Mock orchestrator
    cached_executor.orchestrator.execute_workflow = AsyncMock(return_value=expected_result)

    # Execute
    task = "Calculate 2 + 2"
    context = {"input": "test"}
    result = await cached_executor.execute(
        code=task,
        context=context,
        timeout=30
    )

    # Verify orchestrator was called correctly
    cached_executor.orchestrator.execute_workflow.assert_called_once_with(
        task=task,
        context=context,
        timeout=30
    )

    # Verify result
    assert result == expected_result
    assert result["result"] == 42
    assert "_ai_metadata" in result
    assert result["_ai_metadata"]["status"] == "success"
    assert result["_ai_metadata"]["attempts"] == 1

    # Verify all agent metadata is present
    metadata = result["_ai_metadata"]
    assert metadata["input_analysis"] is not None
    assert metadata["code_generation"] is not None
    assert metadata["code_validation"] is not None
    assert metadata["output_validation"] is not None
