"""Tests para CodeGeneratorAgent"""

import pytest
import json
from unittest.mock import Mock, AsyncMock
from src.core.agents.code_generator import CodeGeneratorAgent


@pytest.fixture
def mock_openai_client():
    client = Mock()
    client.chat = Mock()
    client.chat.completions = Mock()
    return client


@pytest.fixture
def code_generator(mock_openai_client):
    return CodeGeneratorAgent(mock_openai_client)


@pytest.mark.asyncio
async def test_code_generator_simple_task(code_generator, mock_openai_client):
    """Genera código para tarea simple"""

    # Mock respuesta
    mock_response = Mock()
    mock_response.choices = [Mock()]
    mock_response.choices[0].message.content = """
result = context['num1'] + context['num2']
context['sum'] = result
"""
    mock_response.choices[0].message.tool_calls = None

    mock_openai_client.chat.completions.create = AsyncMock(return_value=mock_response)

    # Ejecutar con nueva firma
    response = await code_generator.execute(
        task="Suma estos números",
        functional_context={"num1": 5, "num2": 10},
        config_context={},
        accumulated_insights={},
        error_history=[]
    )

    assert response.success is True
    assert "context['sum']" in response.data["code"]
    assert response.data["tool_calls"] == []


@pytest.mark.asyncio
async def test_code_generator_with_error_history(code_generator, mock_openai_client):
    """Usa error_history para corregir en retry"""

    mock_response = Mock()
    mock_response.choices = [Mock()]
    mock_response.choices[0].message.content = "# código corregido"
    mock_response.choices[0].message.tool_calls = None

    mock_openai_client.chat.completions.create = AsyncMock(return_value=mock_response)

    error_history = [
        {"stage": "code_validation", "errors": ["Variable 'x' no definida"]}
    ]

    response = await code_generator.execute(
        task="Test",
        functional_context={"data": "test"},
        config_context={},
        accumulated_insights={},
        error_history=error_history
    )

    # Verificar que el prompt incluye los errores
    call_args = mock_openai_client.chat.completions.create.call_args
    prompt = call_args[1]["messages"][1]["content"]

    assert "ERRORES PREVIOS" in prompt
    assert "Variable 'x' no definida" in prompt


@pytest.mark.asyncio
async def test_code_generator_extracts_code_from_markdown(code_generator, mock_openai_client):
    """Extrae código limpiando markdown"""

    mock_response = Mock()
    mock_response.choices = [Mock()]
    mock_response.choices[0].message.content = "```python\nprint('test')\n```"
    mock_response.choices[0].message.tool_calls = None

    mock_openai_client.chat.completions.create = AsyncMock(return_value=mock_response)

    response = await code_generator.execute(
        task="Test",
        functional_context={"data": "test"},
        config_context={},
        accumulated_insights={}
    )

    assert response.success is True
    assert response.data["code"] == "print('test')"
    assert "```" not in response.data["code"]
