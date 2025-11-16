"""Tests para DataAnalyzerAgent

NOTA: DataAnalyzer ahora solo genera código de análisis, NO ejecuta E2B.
La ejecución en E2B se hace en el Orchestrator.
"""

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
    """E2B executor (ya no se usa en DataAnalyzer pero necesario para constructor)"""
    executor = Mock()
    return executor


@pytest.fixture
def data_analyzer(mock_openai_client, mock_e2b_executor):
    return DataAnalyzerAgent(mock_openai_client, mock_e2b_executor)


@pytest.mark.asyncio
async def test_data_analyzer_generates_code(data_analyzer, mock_openai_client):
    """Genera código de análisis correctamente"""

    # Mock: código generado por IA
    mock_code_response = Mock()
    mock_code_response.choices = [Mock()]
    mock_code_response.choices[0].message.content = """
import fitz
import base64
import json

pdf_bytes = base64.b64decode(context['pdf_data_b64'])
doc = fitz.open(stream=pdf_bytes, filetype="pdf")

insights = {"type": "pdf", "pages": len(doc)}

print(json.dumps({"insights": insights}, ensure_ascii=False))
"""
    mock_code_response.usage = Mock()
    mock_code_response.usage.prompt_tokens = 400
    mock_code_response.usage.completion_tokens = 100

    mock_openai_client.chat.completions.create = AsyncMock(return_value=mock_code_response)

    # Ejecutar
    context_state = ContextState(
        initial={"pdf_data_b64": "JVBERi0x..."},
        current={"pdf_data_b64": "JVBERi0x..."}
    )

    response = await data_analyzer.execute(context_state)

    assert response.success is True
    assert "analysis_code" in response.data
    assert "import fitz" in response.data["analysis_code"]
    assert "model" in response.data
    assert response.data["model"] == "gpt-4o-mini"


@pytest.mark.asyncio
async def test_data_analyzer_handles_ai_error(data_analyzer, mock_openai_client):
    """Maneja errores de IA correctamente"""

    # Mock: IA falla
    mock_openai_client.chat.completions.create = AsyncMock(
        side_effect=Exception("OpenAI API timeout")
    )

    context_state = ContextState(
        initial={"data": "test"},
        current={"data": "test"}
    )

    response = await data_analyzer.execute(context_state)

    assert response.success is False
    assert "OpenAI API timeout" in response.error


@pytest.mark.asyncio
async def test_data_analyzer_cleans_markdown(data_analyzer, mock_openai_client):
    """Limpia markdown del código generado"""

    # Mock: código con markdown
    mock_code_response = Mock()
    mock_code_response.choices = [Mock()]
    mock_code_response.choices[0].message.content = """```python
import json
insights = {"type": "test"}
print(json.dumps({"insights": insights}))
```"""
    mock_code_response.usage = Mock()
    mock_code_response.usage.prompt_tokens = 100
    mock_code_response.usage.completion_tokens = 50

    mock_openai_client.chat.completions.create = AsyncMock(return_value=mock_code_response)

    context_state = ContextState(
        initial={"data": "test"},
        current={"data": "test"}
    )

    response = await data_analyzer.execute(context_state)

    assert response.success is True
    # Verificar que el código fue limpiado (no tiene ```)
    assert "```" not in response.data["analysis_code"]
    assert "import json" in response.data["analysis_code"]


@pytest.mark.asyncio
async def test_data_analyzer_with_error_history(data_analyzer, mock_openai_client):
    """Genera código con error_history para retry"""

    mock_code_response = Mock()
    mock_code_response.choices = [Mock()]
    mock_code_response.choices[0].message.content = "import json\ninsights = {'type': 'test'}\nprint(json.dumps({'insights': insights}))"
    mock_code_response.usage = Mock()
    mock_code_response.usage.prompt_tokens = 500
    mock_code_response.usage.completion_tokens = 80

    mock_openai_client.chat.completions.create = AsyncMock(return_value=mock_code_response)

    context_state = ContextState(
        initial={"data": "test"},
        current={"data": "test"}
    )

    error_history = [
        {
            "stage": "analysis_validation",
            "error": "type='unknown' no es útil",
            "suggestions": ["Detecta el tipo real de data"]
        }
    ]

    response = await data_analyzer.execute(context_state, error_history=error_history)

    assert response.success is True
    assert "analysis_code" in response.data

    # Verificar que el prompt incluyó los errores
    call_args = mock_openai_client.chat.completions.create.call_args
    prompt = call_args.kwargs["messages"][1]["content"]
    assert "ERRORES PREVIOS" in prompt
