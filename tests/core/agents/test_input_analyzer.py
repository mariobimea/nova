"""Tests para InputAnalyzerAgent"""

import pytest
import json
from unittest.mock import Mock, AsyncMock
from src.core.agents.input_analyzer import InputAnalyzerAgent
from src.core.agents.state import ContextState


@pytest.fixture
def mock_openai_client():
    """Mock de OpenAI client"""
    client = Mock()
    client.chat = Mock()
    client.chat.completions = Mock()
    return client


@pytest.fixture
def input_analyzer(mock_openai_client):
    """InputAnalyzerAgent con OpenAI mockeado"""
    return InputAnalyzerAgent(mock_openai_client)


@pytest.mark.asyncio
async def test_input_analyzer_simple_task(input_analyzer, mock_openai_client):
    """Tarea simple no necesita análisis"""

    # Mock de respuesta de OpenAI
    mock_response = Mock()
    mock_response.choices = [Mock()]
    mock_response.choices[0].message.content = json.dumps({
        "needs_analysis": False,
        "complexity": "simple",
        "reasoning": "Tarea trivial con valores simples"
    })
    mock_response.usage = Mock()
    mock_response.usage.prompt_tokens = 100
    mock_response.usage.completion_tokens = 50

    mock_openai_client.chat.completions.create = AsyncMock(return_value=mock_response)

    # Ejecutar
    context_state = ContextState(
        initial={"num1": 5, "num2": 10},
        current={"num1": 5, "num2": 10}
    )

    response = await input_analyzer.execute(
        task="Suma estos dos números",
        context_state=context_state
    )

    assert response.success is True
    assert response.data["needs_analysis"] is False
    assert response.data["complexity"] == "simple"


@pytest.mark.asyncio
async def test_input_analyzer_complex_task_pdf(input_analyzer, mock_openai_client):
    """PDF necesita análisis"""

    mock_response = Mock()
    mock_response.choices = [Mock()]
    mock_response.choices[0].message.content = json.dumps({
        "needs_analysis": True,
        "complexity": "complex",
        "reasoning": "Es un PDF, necesitamos entender su estructura"
    })
    mock_response.usage = Mock()
    mock_response.usage.prompt_tokens = 200
    mock_response.usage.completion_tokens = 80

    mock_openai_client.chat.completions.create = AsyncMock(return_value=mock_response)

    context_state = ContextState(
        initial={"pdf_data_b64": "JVBERi0x..."},
        current={"pdf_data_b64": "JVBERi0x..."}
    )

    response = await input_analyzer.execute(
        task="Extrae el total de esta factura",
        context_state=context_state
    )

    assert response.success is True
    assert response.data["needs_analysis"] is True
    assert response.data["complexity"] == "complex"


@pytest.mark.asyncio
async def test_input_analyzer_handles_openai_error(input_analyzer, mock_openai_client):
    """Maneja errores de OpenAI correctamente"""

    mock_openai_client.chat.completions.create = AsyncMock(
        side_effect=Exception("OpenAI API error")
    )

    context_state = ContextState(
        initial={"key": "value"},
        current={"key": "value"}
    )

    response = await input_analyzer.execute(
        task="Test task",
        context_state=context_state
    )

    assert response.success is False
    assert "OpenAI API error" in response.error


@pytest.mark.asyncio
async def test_input_analyzer_invalid_response_structure(input_analyzer, mock_openai_client):
    """Maneja respuesta inválida de OpenAI"""

    # Respuesta sin las keys requeridas
    mock_response = Mock()
    mock_response.choices = [Mock()]
    mock_response.choices[0].message.content = json.dumps({
        "needs_analysis": True
        # Falta complexity y reasoning
    })

    mock_openai_client.chat.completions.create = AsyncMock(return_value=mock_response)

    context_state = ContextState(
        initial={"key": "value"},
        current={"key": "value"}
    )

    response = await input_analyzer.execute(
        task="Test",
        context_state=context_state
    )

    assert response.success is False
    assert "Respuesta inválida" in response.error
