"""Tests para OutputValidatorAgent"""

import pytest
import json
from unittest.mock import Mock, AsyncMock
from src.core.agents.output_validator import OutputValidatorAgent


@pytest.fixture
def mock_openai_client():
    client = Mock()
    client.chat = Mock()
    client.chat.completions = Mock()
    return client


@pytest.fixture
def output_validator(mock_openai_client):
    return OutputValidatorAgent(mock_openai_client)


@pytest.mark.asyncio
async def test_output_validator_valid_result(output_validator, mock_openai_client):
    """Resultado válido pasa validación"""

    # Mock respuesta
    mock_response = Mock()
    mock_response.choices = [Mock()]
    mock_response.choices[0].message.content = json.dumps({
        "valid": True,
        "reason": "Total extraído correctamente"
    })
    mock_response.usage = Mock()
    mock_response.usage.prompt_tokens = 200
    mock_response.usage.completion_tokens = 30

    mock_openai_client.chat.completions.create = AsyncMock(return_value=mock_response)

    # Ejecutar
    functional_context_before = {"pdf_data": "..."}
    functional_context_after = {"pdf_data": "...", "total_amount": "1234.56"}

    response = await output_validator.execute(
        task="Extrae el total de la factura",
        functional_context_before=functional_context_before,
        functional_context_after=functional_context_after,
        code_executed="context['total_amount'] = '1234.56'",
        execution_result={"success": True, "status": "completed"}
    )

    assert response.success is True
    assert response.data["valid"] is True
    assert "total_amount" in response.data["changes_detected"]


@pytest.mark.asyncio
async def test_output_validator_no_changes(output_validator, mock_openai_client):
    """Detecta cuando no hay cambios"""

    mock_response = Mock()
    mock_response.choices = [Mock()]
    mock_response.choices[0].message.content = json.dumps({
        "valid": False,
        "reason": "No se realizaron cambios en el contexto"
    })
    mock_response.usage = Mock()
    mock_response.usage.prompt_tokens = 150
    mock_response.usage.completion_tokens = 25

    mock_openai_client.chat.completions.create = AsyncMock(return_value=mock_response)

    # Contextos idénticos
    context = {"data": "test"}

    response = await output_validator.execute(
        task="Procesa esto",
        functional_context_before=context,
        functional_context_after=context,
        code_executed="# No changes",
        execution_result={"success": True, "status": "completed"}
    )

    assert response.success is True
    assert response.data["valid"] is False
    assert len(response.data["changes_detected"]) == 0


@pytest.mark.asyncio
async def test_output_validator_incomplete_task(output_validator, mock_openai_client):
    """Detecta tarea incompleta"""

    mock_response = Mock()
    mock_response.choices = [Mock()]
    mock_response.choices[0].message.content = json.dumps({
        "valid": False,
        "reason": "La tarea pedía 'total' pero solo se agregó 'currency'"
    })
    mock_response.usage = Mock()
    mock_response.usage.prompt_tokens = 180
    mock_response.usage.completion_tokens = 28

    mock_openai_client.chat.completions.create = AsyncMock(return_value=mock_response)

    functional_context_before = {"data": "test"}
    functional_context_after = {"data": "test", "currency": "USD"}  # Falta el total

    response = await output_validator.execute(
        task="Extrae el total y la moneda",
        functional_context_before=functional_context_before,
        functional_context_after=functional_context_after,
        code_executed="context['currency'] = 'USD'",
        execution_result={"success": True, "status": "completed"}
    )

    assert response.success is True
    assert response.data["valid"] is False


@pytest.mark.asyncio
async def test_output_validator_handles_openai_error(output_validator, mock_openai_client):
    """Maneja errores de OpenAI"""

    mock_openai_client.chat.completions.create = AsyncMock(
        side_effect=Exception("OpenAI API error")
    )

    response = await output_validator.execute(
        task="Test",
        functional_context_before={"a": 1},
        functional_context_after={"a": 1, "b": 2},
        code_executed="context['b'] = 2",
        execution_result={"success": True, "status": "completed"}
    )

    assert response.success is False
    assert "OpenAI API error" in response.error
