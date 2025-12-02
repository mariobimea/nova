"""Tests para AnalysisValidatorAgent"""

import pytest
from unittest.mock import Mock, AsyncMock
from src.core.agents.analysis_validator import AnalysisValidatorAgent


@pytest.fixture
def mock_openai_client():
    client = Mock()
    client.chat = Mock()
    client.chat.completions = Mock()
    return client


@pytest.fixture
def analysis_validator(mock_openai_client):
    return AnalysisValidatorAgent(mock_openai_client)


@pytest.mark.asyncio
async def test_analysis_validator_valid_pdf_insights(analysis_validator, mock_openai_client):
    """Insights de PDF completos son válidos"""

    # Mock: respuesta de IA indica que los insights son válidos
    mock_response = Mock()
    mock_response.choices = [Mock()]
    mock_response.choices[0].message.content = """
    {
        "valid": true,
        "reason": "Los insights contienen información útil sobre el PDF: número de páginas, presencia de capa de texto, y nombre del archivo. Esta metadata será útil para el CodeGenerator."
    }
    """
    mock_response.usage = Mock()
    mock_response.usage.prompt_tokens = 300
    mock_response.usage.completion_tokens = 50

    mock_openai_client.chat.completions.create = AsyncMock(return_value=mock_response)

    # Ejecutar con nueva firma
    response = await analysis_validator.execute(
        task="Extract text from PDF document",
        functional_context_before={
            "attachments": [{"data": "<base64 PDF>", "filename": "invoice.pdf"}]
        },
        insights={
            "type": "pdf",
            "pages": 3,
            "has_text_layer": True,
            "filename": "invoice.pdf"
        },
        analysis_code="import fitz...",
        execution_result={"success": True, "status": "completed"}
    )

    assert response.success is True
    assert response.data["valid"] is True
    assert "útil" in response.data["reason"] or "useful" in response.data["reason"]
    assert "model" in response.data
    assert response.data["model"] == "gpt-4o-mini"


@pytest.mark.asyncio
async def test_analysis_validator_invalid_unknown_type(analysis_validator, mock_openai_client):
    """Insights con type='unknown' son inválidos"""

    # Mock: respuesta indica que los insights son inválidos
    mock_response = Mock()
    mock_response.choices = [Mock()]
    mock_response.choices[0].message.content = """
    {
        "valid": false,
        "reason": "El tipo de data es 'unknown', lo que indica que el análisis falló en detectar el tipo real de data. Los insights no proporcionan información útil.",
        "suggestions": [
            "Usa PyMuPDF para detectar si es un PDF",
            "Verifica el formato del archivo en context['attachments'][0]"
        ]
    }
    """
    mock_response.usage = Mock()
    mock_response.usage.prompt_tokens = 300
    mock_response.usage.completion_tokens = 80

    mock_openai_client.chat.completions.create = AsyncMock(return_value=mock_response)

    # Ejecutar
    response = await analysis_validator.execute(
        task="Extract text from PDF",
        functional_context_before={
            "attachments": [{"data": "<base64 PDF>"}]
        },
        insights={"type": "unknown"},
        analysis_code="# analysis code",
        execution_result={"success": True, "status": "completed"}
    )

    assert response.success is True
    assert response.data["valid"] is False
    assert "unknown" in response.data["reason"]
    assert "suggestions" in response.data
    assert len(response.data["suggestions"]) > 0


@pytest.mark.asyncio
async def test_analysis_validator_invalid_missing_metadata(analysis_validator, mock_openai_client):
    """PDF sin metadata esencial es inválido"""

    # Mock: respuesta indica falta metadata
    mock_response = Mock()
    mock_response.choices = [Mock()]
    mock_response.choices[0].message.content = """
    {
        "valid": false,
        "reason": "Aunque detectó que es un PDF, faltan metadatos esenciales como 'pages' y 'has_text_layer' que son críticos para procesar el documento.",
        "suggestions": [
            "Agrega 'pages': len(doc) para saber cuántas páginas tiene",
            "Agrega 'has_text_layer': bool(doc[0].get_text()) para saber si tiene texto extraíble"
        ]
    }
    """
    mock_response.usage = Mock()
    mock_response.usage.prompt_tokens = 320
    mock_response.usage.completion_tokens = 90

    mock_openai_client.chat.completions.create = AsyncMock(return_value=mock_response)

    # Ejecutar
    response = await analysis_validator.execute(
        task="Extract text from PDF",
        functional_context_before={
            "attachments": [{"data": "<base64 PDF>"}]
        },
        insights={"type": "pdf"},  # Sin pages, has_text_layer, etc.
        analysis_code="# analysis code",
        execution_result={"success": True, "status": "completed"}
    )

    assert response.success is True
    assert response.data["valid"] is False
    assert "metadata" in response.data["reason"].lower() or "metadatos" in response.data["reason"].lower()
    assert len(response.data["suggestions"]) > 0


@pytest.mark.asyncio
async def test_analysis_validator_with_error_in_insights(analysis_validator, mock_openai_client):
    """Insights con error son inválidos"""

    mock_response = Mock()
    mock_response.choices = [Mock()]
    mock_response.choices[0].message.content = """
    {
        "valid": false,
        "reason": "Los insights contienen un error que indica que el análisis falló completamente. El código no pudo procesar la data.",
        "suggestions": [
            "Verifica que el código acceda correctamente a context['attachments']",
            "Asegúrate de decodificar el base64 antes de procesar"
        ]
    }
    """
    mock_response.usage = Mock()
    mock_response.usage.prompt_tokens = 300
    mock_response.usage.completion_tokens = 70

    mock_openai_client.chat.completions.create = AsyncMock(return_value=mock_response)

    # Ejecutar
    response = await analysis_validator.execute(
        task="Analyze PDF",
        functional_context_before={},
        insights={
            "type": "unknown",
            "error": "Could not parse PDF"
        },
        analysis_code="# failed analysis",
        execution_result={"success": False, "error": "Could not parse PDF"}
    )

    assert response.success is True
    assert response.data["valid"] is False


@pytest.mark.asyncio
async def test_analysis_validator_handles_ai_error(analysis_validator, mock_openai_client):
    """Maneja errores de la IA correctamente"""

    # Mock: IA falla
    mock_openai_client.chat.completions.create = AsyncMock(
        side_effect=Exception("OpenAI API timeout")
    )

    # Ejecutar
    response = await analysis_validator.execute(
        task="Test",
        functional_context_before={},
        insights={"type": "test"},
        analysis_code="# test code",
        execution_result={"success": True}
    )

    assert response.success is False
    assert "OpenAI API timeout" in response.error
