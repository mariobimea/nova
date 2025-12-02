"""Tests para CodeGeneratorAgent con RAG integration"""

import pytest
from unittest.mock import Mock, AsyncMock
from src.core.agents.code_generator import CodeGeneratorAgent


@pytest.fixture
def mock_openai_client():
    client = Mock()
    client.chat = Mock()
    client.chat.completions = Mock()
    return client


@pytest.fixture
def mock_rag_client():
    """Mock RAGClient"""
    client = AsyncMock()
    client.search = AsyncMock()
    return client


@pytest.fixture
def code_generator_with_rag(mock_openai_client, mock_rag_client):
    """CodeGenerator con RAGClient mockeado"""
    return CodeGeneratorAgent(mock_openai_client, mock_rag_client)


@pytest.mark.asyncio
async def test_code_generator_with_rag_tool_calling(code_generator_with_rag, mock_openai_client, mock_rag_client):
    """Verifica que CodeGenerator llama a RAG cuando GPT usa search_documentation"""

    # Mock GPT response con tool call
    mock_tool_call = Mock()
    mock_tool_call.function.name = "search_documentation"
    mock_tool_call.function.arguments = '{"library": "pymupdf", "query": "extract text from PDF", "top_k": 3}'

    mock_response_1 = Mock()
    mock_response_1.choices = [Mock()]
    mock_response_1.choices[0].message.tool_calls = [mock_tool_call]
    mock_response_1.choices[0].message.content = ""

    # Mock GPT response después de recibir docs
    mock_response_2 = Mock()
    mock_response_2.choices = [Mock()]
    mock_response_2.choices[0].message.content = """
import fitz
doc = fitz.open(context['pdf_path'])
text = doc[0].get_text()
context['ocr_text'] = text
"""
    mock_response_2.choices[0].message.tool_calls = None

    mock_openai_client.chat.completions.create = AsyncMock(
        side_effect=[mock_response_1, mock_response_2]
    )

    # Mock RAG response
    mock_rag_client.search.return_value = [
        {
            "text": "Example: doc = fitz.open('file.pdf')\ntext = doc[0].get_text()",
            "source": "pymupdf",
            "topic": "quickstart",
            "score": 0.95
        }
    ]

    # Ejecutar con nueva firma
    response = await code_generator_with_rag.execute(
        task="Extract text from PDF",
        functional_context={"pdf_path": "/tmp/test.pdf"},
        config_context={},
        accumulated_insights={}
    )

    # Verificar que llamó a RAG
    mock_rag_client.search.assert_called_once_with(
        query="extract text from PDF",
        library="pymupdf",
        top_k=3
    )

    # Verificar que guardó la info del tool call
    assert response.success is True
    assert len(response.data["tool_calls"]) == 1
    assert response.data["tool_calls"][0]["function"] == "search_documentation"
    assert response.data["tool_calls"][0]["arguments"]["library"] == "pymupdf"

    # Verificar que el código fue generado
    assert "fitz" in response.data["code"]


@pytest.mark.asyncio
async def test_code_generator_without_rag_client(mock_openai_client):
    """CodeGenerator funciona sin RAGClient (sin tool calling)"""

    # CodeGenerator SIN rag_client
    code_generator = CodeGeneratorAgent(mock_openai_client, rag_client=None)

    # Mock GPT response SIN tool calls
    mock_response = Mock()
    mock_response.choices = [Mock()]
    mock_response.choices[0].message.content = "context['result'] = 42"
    mock_response.choices[0].message.tool_calls = None

    mock_openai_client.chat.completions.create = AsyncMock(return_value=mock_response)

    # Ejecutar
    response = await code_generator.execute(
        task="Calculate result",
        functional_context={"input": "test"},
        config_context={},
        accumulated_insights={}
    )

    # Verificar que funcionó sin RAG
    assert response.success is True
    assert response.data["tool_calls"] == []
    assert "result" in response.data["code"]


@pytest.mark.asyncio
async def test_code_generator_handles_rag_errors(code_generator_with_rag, mock_openai_client, mock_rag_client):
    """CodeGenerator maneja errores de RAG gracefully"""

    # Mock GPT con tool call
    mock_tool_call = Mock()
    mock_tool_call.function.name = "search_documentation"
    mock_tool_call.function.arguments = '{"library": "pymupdf", "query": "test"}'

    mock_response_1 = Mock()
    mock_response_1.choices = [Mock()]
    mock_response_1.choices[0].message.tool_calls = [mock_tool_call]
    mock_response_1.choices[0].message.content = ""

    # Mock GPT response final
    mock_response_2 = Mock()
    mock_response_2.choices = [Mock()]
    mock_response_2.choices[0].message.content = "context['result'] = 'done'"
    mock_response_2.choices[0].message.tool_calls = None

    mock_openai_client.chat.completions.create = AsyncMock(
        side_effect=[mock_response_1, mock_response_2]
    )

    # Mock RAG que falla
    mock_rag_client.search.side_effect = Exception("RAG service down")

    # Ejecutar
    response = await code_generator_with_rag.execute(
        task="Test task",
        functional_context={"input": "test"},
        config_context={},
        accumulated_insights={}
    )

    # Verificar que continuó a pesar del error de RAG
    assert response.success is True
    assert "result" in response.data["code"]

    # El error de RAG se loguea pero no falla la ejecución


@pytest.mark.asyncio
async def test_search_docs_formats_results_correctly(code_generator_with_rag, mock_rag_client):
    """_search_docs formatea correctamente los resultados de RAG"""

    # Mock RAG response
    mock_rag_client.search.return_value = [
        {
            "text": "First example code",
            "source": "pymupdf",
            "topic": "quickstart",
            "score": 0.95
        },
        {
            "text": "Second example code",
            "source": "pymupdf",
            "topic": "advanced",
            "score": 0.82
        }
    ]

    # Ejecutar
    result = await code_generator_with_rag._search_docs("pymupdf", "test query", top_k=2)

    # Verificar formato
    assert "### Ejemplo 1 (relevancia: 95%)" in result
    assert "### Ejemplo 2 (relevancia: 82%)" in result
    assert "First example code" in result
    assert "Second example code" in result
    assert "Fuente: pymupdf - quickstart" in result


@pytest.mark.asyncio
async def test_search_docs_handles_empty_results(code_generator_with_rag, mock_rag_client):
    """_search_docs maneja resultados vacíos"""

    # Mock RAG sin resultados
    mock_rag_client.search.return_value = []

    # Ejecutar
    result = await code_generator_with_rag._search_docs("pymupdf", "test query")

    # Verificar mensaje de no encontrado
    assert "No se encontró documentación" in result
    assert "pymupdf" in result


@pytest.mark.asyncio
async def test_tool_definition_has_correct_schema(code_generator_with_rag):
    """Tool definition tiene el schema correcto"""

    tools = code_generator_with_rag.tools
    assert len(tools) == 1

    tool = tools[0]
    assert tool["type"] == "function"
    assert tool["function"]["name"] == "search_documentation"

    # Verificar parámetros
    params = tool["function"]["parameters"]["properties"]
    assert "library" in params
    assert "query" in params
    assert "top_k" in params

    # Verificar enum de libraries
    assert params["library"]["enum"] == ["pymupdf", "easyocr", "email", "gmail"]

    # Verificar required
    required = tool["function"]["parameters"]["required"]
    assert "library" in required
    assert "query" in required
