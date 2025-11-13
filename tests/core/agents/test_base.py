"""Tests para BaseAgent y AgentResponse"""

import pytest
from src.core.agents.base import BaseAgent, AgentResponse


def test_agent_response_success():
    """AgentResponse con success=True"""
    response = AgentResponse(
        success=True,
        data={"result": 42},
        execution_time_ms=123.45,
        agent_name="TestAgent"
    )

    assert response.success is True
    assert response.data["result"] == 42
    assert response.error is None


def test_agent_response_failure():
    """AgentResponse con success=False requiere error"""
    response = AgentResponse(
        success=False,
        data={},
        error="Something went wrong",
        execution_time_ms=50.0
    )

    assert response.success is False
    assert response.error == "Something went wrong"


def test_agent_response_failure_without_error_raises():
    """AgentResponse con success=False sin error debe fallar"""
    with pytest.raises(ValueError, match="debe proporcionar un error"):
        AgentResponse(success=False, data={})


class TestAgent(BaseAgent):
    """Agente de prueba para testing"""
    async def execute(self, value: int) -> AgentResponse:
        return self._create_response(
            success=True,
            data={"doubled": value * 2},
            execution_time_ms=10.0
        )


@pytest.mark.asyncio
async def test_base_agent_execute():
    """BaseAgent.execute() funciona"""
    agent = TestAgent()
    response = await agent.execute(value=21)

    assert response.success is True
    assert response.data["doubled"] == 42
    assert response.agent_name == "TestAgent"


@pytest.mark.asyncio
async def test_base_agent_create_response():
    """_create_response() helper funciona"""
    agent = TestAgent()

    response = agent._create_response(
        success=True,
        data={"key": "value"},
        execution_time_ms=100.0
    )

    assert response.success is True
    assert response.data["key"] == "value"
    assert response.execution_time_ms == 100.0
    assert response.agent_name == "TestAgent"
