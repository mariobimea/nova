"""Tests para DataAnalyzerAgent"""

import pytest
from unittest.mock import Mock, AsyncMock
from src.core.agents.data_analyzer import DataAnalyzerAgent
from src.core.agents.state import ContextState


@pytest.fixture
def mock_openai_client():
    client = Mock()
    client.chat = Mock()
    client.chat.completions = Mock()
    return client


@pytest.fixture
def mock_e2b_executor():
    executor = Mock()
    executor.execute_code = AsyncMock()
    return executor


@pytest.fixture
def data_analyzer(mock_openai_client, mock_e2b_executor):
    return DataAnalyzerAgent(mock_openai_client, mock_e2b_executor)


@pytest.mark.asyncio
async def test_data_analyzer_pdf(data_analyzer, mock_openai_client, mock_e2b_executor):
    """Analiza PDF correctamente"""

    # Mock: código generado por IA
    mock_code_response = Mock()
    mock_code_response.choices = [Mock()]
    mock_code_response.choices[0].message.content = """
import fitz
insights = {"type": "pdf", "pages": 3}
"""
    mock_openai_client.chat.completions.create = AsyncMock(return_value=mock_code_response)

    # Mock: resultado de E2B
    mock_e2b_executor.execute_code.return_value = {
        "pdf_data_b64": "...",
        "insights": {
            "type": "pdf",
            "pages": 3,
            "has_text_layer": True
        }
    }

    # Ejecutar
    context_state = ContextState(
        initial={"pdf_data_b64": "JVBERi0x..."},
        current={"pdf_data_b64": "JVBERi0x..."}
    )

    response = await data_analyzer.execute(context_state)

    assert response.success is True
    assert response.data["type"] == "pdf"
    assert response.data["pages"] == 3
    assert "analysis_code" in response.data


@pytest.mark.asyncio
async def test_data_analyzer_e2b_execution_error(data_analyzer, mock_openai_client, mock_e2b_executor):
    """Error en E2B se maneja correctamente"""

    # Mock: código generado
    mock_code_response = Mock()
    mock_code_response.choices = [Mock()]
    mock_code_response.choices[0].message.content = "insights = {}"
    mock_openai_client.chat.completions.create = AsyncMock(return_value=mock_code_response)

    # Mock: E2B falla
    mock_e2b_executor.execute_code.side_effect = Exception("E2B timeout")

    context_state = ContextState(
        initial={"data": "test"},
        current={"data": "test"}
    )

    response = await data_analyzer.execute(context_state)

    assert response.success is False
    assert "E2B timeout" in response.error


@pytest.mark.asyncio
async def test_data_analyzer_cleans_markdown(data_analyzer, mock_openai_client, mock_e2b_executor):
    """Limpia markdown del código generado"""

    # Mock: código con markdown
    mock_code_response = Mock()
    mock_code_response.choices = [Mock()]
    mock_code_response.choices[0].message.content = """```python
insights = {"type": "test"}
```"""
    mock_openai_client.chat.completions.create = AsyncMock(return_value=mock_code_response)

    # Mock: E2B retorna insights
    mock_e2b_executor.execute_code.return_value = {
        "insights": {"type": "test"}
    }

    context_state = ContextState(
        initial={"data": "test"},
        current={"data": "test"}
    )

    response = await data_analyzer.execute(context_state)

    assert response.success is True
    # Verificar que el código fue limpiado (no tiene ```)
    assert "```" not in response.data["analysis_code"]


@pytest.mark.asyncio
async def test_data_analyzer_fallback_when_no_insights(data_analyzer, mock_openai_client, mock_e2b_executor):
    """Usa fallback cuando no encuentra insights"""

    mock_code_response = Mock()
    mock_code_response.choices = [Mock()]
    mock_code_response.choices[0].message.content = "print('test')"
    mock_openai_client.chat.completions.create = AsyncMock(return_value=mock_code_response)

    # Mock: E2B no retorna insights
    mock_e2b_executor.execute_code.return_value = {
        "data": "test"
        # No hay 'insights' key
    }

    context_state = ContextState(
        initial={"data": "test"},
        current={"data": "test"}
    )

    response = await data_analyzer.execute(context_state)

    assert response.success is True
    assert response.data["type"] == "unknown"
