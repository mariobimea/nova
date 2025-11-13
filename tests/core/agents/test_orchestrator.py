"""Tests para MultiAgentOrchestrator"""

import pytest
from unittest.mock import Mock, AsyncMock
from src.core.agents.orchestrator import MultiAgentOrchestrator
from src.core.agents.base import AgentResponse


@pytest.fixture
def mock_agents():
    """Crea mocks de todos los agentes"""
    return {
        "input_analyzer": Mock(),
        "data_analyzer": Mock(),
        "code_generator": Mock(),
        "code_validator": Mock(),
        "output_validator": Mock(),
        "e2b_executor": Mock()
    }


@pytest.fixture
def orchestrator(mock_agents):
    """Orchestrator con agentes mockeados"""
    return MultiAgentOrchestrator(
        input_analyzer=mock_agents["input_analyzer"],
        data_analyzer=mock_agents["data_analyzer"],
        code_generator=mock_agents["code_generator"],
        code_validator=mock_agents["code_validator"],
        output_validator=mock_agents["output_validator"],
        e2b_executor=mock_agents["e2b_executor"],
        max_retries=3
    )


@pytest.mark.asyncio
async def test_orchestrator_simple_flow_success(orchestrator, mock_agents):
    """Flujo completo exitoso sin retries"""

    # Mock InputAnalyzer - no necesita análisis
    mock_agents["input_analyzer"].execute = AsyncMock(return_value=AgentResponse(
        success=True,
        data={"needs_analysis": False, "complexity": "simple"},
        execution_time_ms=10.0,
        agent_name="InputAnalyzer"
    ))

    # Mock CodeGenerator
    mock_agents["code_generator"].execute = AsyncMock(return_value=AgentResponse(
        success=True,
        data={"code": "context['result'] = 42", "tool_calls": []},
        execution_time_ms=100.0,
        agent_name="CodeGenerator"
    ))

    # Mock CodeValidator
    mock_agents["code_validator"].execute = AsyncMock(return_value=AgentResponse(
        success=True,
        data={"valid": True, "errors": [], "checks_passed": ["syntax"]},
        execution_time_ms=5.0,
        agent_name="CodeValidator"
    ))

    # Mock E2B
    mock_agents["e2b_executor"].execute_code = AsyncMock(
        return_value={"input": "test", "result": 42}
    )

    # Mock OutputValidator
    mock_agents["output_validator"].execute = AsyncMock(return_value=AgentResponse(
        success=True,
        data={"valid": True, "reason": "Task completed", "changes_detected": ["result"]},
        execution_time_ms=10.0,
        agent_name="OutputValidator"
    ))

    # Ejecutar
    result = await orchestrator.execute_workflow(
        task="Calculate result",
        context={"input": "test"},
        timeout=30
    )

    # Verificar
    assert result["result"] == 42
    assert "_ai_metadata" in result
    assert result["_ai_metadata"]["attempts"] == 1
    assert "input_analysis" in result["_ai_metadata"]


@pytest.mark.asyncio
async def test_orchestrator_with_data_analysis(orchestrator, mock_agents):
    """Flujo con DataAnalyzer cuando needs_analysis=True"""

    # Mock InputAnalyzer - necesita análisis
    mock_agents["input_analyzer"].execute = AsyncMock(return_value=AgentResponse(
        success=True,
        data={"needs_analysis": True, "complexity": "complex"},
        execution_time_ms=10.0,
        agent_name="InputAnalyzer"
    ))

    # Mock DataAnalyzer
    mock_agents["data_analyzer"].execute = AsyncMock(return_value=AgentResponse(
        success=True,
        data={"type": "pdf", "pages": 1},
        execution_time_ms=50.0,
        agent_name="DataAnalyzer"
    ))

    # Mock rest of agents (simple success path)
    mock_agents["code_generator"].execute = AsyncMock(return_value=AgentResponse(
        success=True,
        data={"code": "context['result'] = 1", "tool_calls": []},
        execution_time_ms=100.0,
        agent_name="CodeGenerator"
    ))

    mock_agents["code_validator"].execute = AsyncMock(return_value=AgentResponse(
        success=True,
        data={"valid": True, "errors": []},
        execution_time_ms=5.0,
        agent_name="CodeValidator"
    ))

    mock_agents["e2b_executor"].execute_code = AsyncMock(
        return_value={"data": "test", "result": 1}
    )

    mock_agents["output_validator"].execute = AsyncMock(return_value=AgentResponse(
        success=True,
        data={"valid": True, "reason": "OK"},
        execution_time_ms=10.0,
        agent_name="OutputValidator"
    ))

    # Ejecutar
    result = await orchestrator.execute_workflow(
        task="Process PDF",
        context={"data": "test"},
        timeout=30
    )

    # Verificar que DataAnalyzer fue llamado
    assert result["_ai_metadata"]["data_analysis"]["type"] == "pdf"
    mock_agents["data_analyzer"].execute.assert_called_once()


@pytest.mark.asyncio
async def test_orchestrator_retry_on_code_validation_error(orchestrator, mock_agents):
    """Retry cuando CodeValidator falla"""

    mock_agents["input_analyzer"].execute = AsyncMock(return_value=AgentResponse(
        success=True,
        data={"needs_analysis": False, "complexity": "simple"},
        execution_time_ms=10.0,
        agent_name="InputAnalyzer"
    ))

    # CodeGenerator - primero genera código inválido, luego válido
    call_count = 0

    async def code_gen_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return AgentResponse(
            success=True,
            data={"code": f"code_v{call_count}", "tool_calls": []},
            execution_time_ms=100.0,
            agent_name="CodeGenerator"
        )

    mock_agents["code_generator"].execute = AsyncMock(side_effect=code_gen_side_effect)

    # CodeValidator - falla primero, luego pasa
    val_call_count = 0

    async def code_val_side_effect(*args, **kwargs):
        nonlocal val_call_count
        val_call_count += 1
        if val_call_count == 1:
            return AgentResponse(
                success=True,
                data={"valid": False, "errors": ["Syntax error"]},
                execution_time_ms=5.0,
                agent_name="CodeValidator"
            )
        return AgentResponse(
            success=True,
            data={"valid": True, "errors": []},
            execution_time_ms=5.0,
            agent_name="CodeValidator"
        )

    mock_agents["code_validator"].execute = AsyncMock(side_effect=code_val_side_effect)

    mock_agents["e2b_executor"].execute_code = AsyncMock(
        return_value={"result": "ok"}
    )

    mock_agents["output_validator"].execute = AsyncMock(return_value=AgentResponse(
        success=True,
        data={"valid": True, "reason": "OK"},
        execution_time_ms=10.0,
        agent_name="OutputValidator"
    ))

    # Ejecutar
    result = await orchestrator.execute_workflow(
        task="Test",
        context={},
        timeout=30
    )

    # Verificar que hubo retry
    assert result["_ai_metadata"]["attempts"] == 2
    assert len(result["_ai_metadata"]["errors"]) == 1
    assert result["_ai_metadata"]["errors"][0]["stage"] == "code_validation"


@pytest.mark.asyncio
async def test_orchestrator_max_retries_exceeded(orchestrator, mock_agents):
    """Falla después de max_retries intentos"""

    mock_agents["input_analyzer"].execute = AsyncMock(return_value=AgentResponse(
        success=True,
        data={"needs_analysis": False, "complexity": "simple"},
        execution_time_ms=10.0,
        agent_name="InputAnalyzer"
    ))

    # CodeGenerator siempre falla
    mock_agents["code_generator"].execute = AsyncMock(return_value=AgentResponse(
        success=False,
        error="Generation failed",
        data={},
        execution_time_ms=100.0,
        agent_name="CodeGenerator"
    ))

    # Ejecutar
    result = await orchestrator.execute_workflow(
        task="Test",
        context={},
        timeout=30
    )

    # Verificar que falló con metadata de error
    assert "_ai_metadata" in result
    assert result["_ai_metadata"]["status"] == "failed"
    assert "final_error" in result["_ai_metadata"]
    assert result["_ai_metadata"]["attempts"] == 3
