"""Tests para RAGClient"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
import httpx

from src.core.integrations.rag_client import RAGClient


@pytest.fixture
def mock_httpx_client():
    """Mock httpx.AsyncClient"""
    with patch("src.core.integrations.rag_client.httpx.AsyncClient") as mock_client:
        # Create mock instance
        mock_instance = AsyncMock()
        mock_client.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def rag_client(mock_httpx_client):
    """RAGClient con httpx mockeado"""
    with patch.dict("os.environ", {"RAG_SERVICE_URL": "https://test-rag.example.com"}):
        client = RAGClient()
        return client


@pytest.mark.asyncio
async def test_rag_client_initialization():
    """RAGClient se inicializa correctamente con URL válida"""
    with patch.dict("os.environ", {"RAG_SERVICE_URL": "https://test.com"}):
        client = RAGClient()
        assert client.base_url == "https://test.com"
        assert client.timeout == 10


@pytest.mark.asyncio
async def test_rag_client_removes_trailing_slash():
    """RAGClient elimina trailing slash de la URL"""
    with patch.dict("os.environ", {"RAG_SERVICE_URL": "https://test.com/"}):
        client = RAGClient()
        assert client.base_url == "https://test.com"


@pytest.mark.asyncio
async def test_rag_client_requires_url():
    """RAGClient falla si no hay RAG_SERVICE_URL"""
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(ValueError) as exc_info:
            RAGClient()
        assert "RAG_SERVICE_URL" in str(exc_info.value)


@pytest.mark.asyncio
async def test_health_check_success(rag_client, mock_httpx_client):
    """health_check retorna status correcto"""

    # Mock response - json() debe retornar valor directo, no coroutine
    mock_response = AsyncMock()
    mock_response.json = lambda: {
        "status": "healthy",
        "vector_store_ready": True,
        "documents_loaded": 100
    }
    mock_response.raise_for_status = lambda: None
    mock_httpx_client.get = AsyncMock(return_value=mock_response)

    # Ejecutar
    result = await rag_client.health_check()

    # Verificar
    assert result["status"] == "healthy"
    assert result["vector_store_ready"] is True
    assert result["documents_loaded"] == 100
    mock_httpx_client.get.assert_called_once_with("https://test-rag.example.com/health")


@pytest.mark.asyncio
async def test_search_success(rag_client, mock_httpx_client):
    """search retorna resultados correctos"""

    # Mock response
    mock_response = AsyncMock()
    mock_response.json = lambda: {
        "results": [
            {
                "text": "Example code for PDF extraction",
                "source": "pymupdf",
                "topic": "quickstart",
                "score": 0.95
            },
            {
                "text": "Advanced PDF processing",
                "source": "pymupdf",
                "topic": "advanced",
                "score": 0.82
            }
        ],
        "query": "extract text from PDF",
        "count": 2
    }
    mock_response.raise_for_status = lambda: None
    mock_httpx_client.post = AsyncMock(return_value=mock_response)

    # Ejecutar
    results = await rag_client.search(
        query="extract text from PDF",
        library="pymupdf",
        top_k=3
    )

    # Verificar
    assert len(results) == 2
    assert results[0]["text"] == "Example code for PDF extraction"
    assert results[0]["score"] == 0.95
    assert results[1]["source"] == "pymupdf"

    # Verificar que llamó con los parámetros correctos
    mock_httpx_client.post.assert_called_once()
    call_args = mock_httpx_client.post.call_args
    assert call_args[0][0] == "https://test-rag.example.com/rag/query"
    assert call_args[1]["json"]["query"] == "extract text from PDF"
    assert call_args[1]["json"]["top_k"] == 3
    assert call_args[1]["json"]["filters"]["source"] == "pymupdf"


@pytest.mark.asyncio
async def test_search_without_filters(rag_client, mock_httpx_client):
    """search funciona sin filtros"""

    mock_response = AsyncMock()
    mock_response.json = lambda: {
        "results": [],
        "query": "test",
        "count": 0
    }
    mock_response.raise_for_status = lambda: None
    mock_httpx_client.post = AsyncMock(return_value=mock_response)

    # Ejecutar sin library ni topic
    results = await rag_client.search(query="test", top_k=5)

    # Verificar que no envía filters
    call_args = mock_httpx_client.post.call_args
    assert "filters" not in call_args[1]["json"]


@pytest.mark.asyncio
async def test_search_clamps_top_k(rag_client, mock_httpx_client):
    """search limita top_k entre 1 y 20"""

    mock_response = AsyncMock()
    mock_response.json = lambda: {"results": [], "query": "test", "count": 0}
    mock_response.raise_for_status = lambda: None
    mock_httpx_client.post = AsyncMock(return_value=mock_response)

    # Test con top_k = 0 (debe ser 1)
    await rag_client.search(query="test", top_k=0)
    call_args = mock_httpx_client.post.call_args
    assert call_args[1]["json"]["top_k"] == 1

    # Test con top_k = 100 (debe ser 20)
    await rag_client.search(query="test", top_k=100)
    call_args = mock_httpx_client.post.call_args
    assert call_args[1]["json"]["top_k"] == 20


@pytest.mark.asyncio
async def test_search_handles_503_error(rag_client, mock_httpx_client):
    """search lanza ValueError cuando RAG no está listo"""

    # Mock 503 error - debe lanzarse desde raise_for_status()
    mock_response = Mock()  # No AsyncMock para response
    mock_response.status_code = 503

    # Crear el error con el response real
    error = httpx.HTTPStatusError(
        "Service Unavailable",
        request=Mock(),
        response=mock_response
    )

    # raise_for_status debe lanzar la excepción
    mock_response.raise_for_status = Mock(side_effect=error)

    # Mock post para retornar este response
    mock_httpx_client.post = AsyncMock(return_value=mock_response)

    # Ejecutar y verificar error
    with pytest.raises(ValueError) as exc_info:
        await rag_client.search(query="test")

    assert "not ready yet" in str(exc_info.value)


@pytest.mark.asyncio
async def test_get_stats_success(rag_client, mock_httpx_client):
    """get_stats retorna estadísticas correctas"""

    mock_response = AsyncMock()
    mock_response.json = lambda: {
        "total_documents": 150,
        "sources": ["pymupdf", "easyocr", "gmail"],
        "topics": ["quickstart", "advanced", "official"],
        "status": "ready"
    }
    mock_response.raise_for_status = lambda: None
    mock_httpx_client.get = AsyncMock(return_value=mock_response)

    # Ejecutar
    stats = await rag_client.get_stats()

    # Verificar
    assert stats["total_documents"] == 150
    assert "pymupdf" in stats["sources"]
    assert stats["status"] == "ready"
    mock_httpx_client.get.assert_called_once_with("https://test-rag.example.com/rag/stats")


@pytest.mark.asyncio
async def test_context_manager(mock_httpx_client):
    """RAGClient funciona como context manager"""

    with patch.dict("os.environ", {"RAG_SERVICE_URL": "https://test.com"}):
        async with RAGClient() as client:
            assert client.base_url == "https://test.com"

        # Verificar que close fue llamado
        mock_httpx_client.aclose.assert_called_once()
