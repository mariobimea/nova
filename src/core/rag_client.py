"""
RAG Client for NOVA

HTTP client to communicate with the nova-rag microservice.
Provides:
- Vector search over documentation for AI code generation (RAGClient)
- Semantic code cache for caching successful code executions (SemanticCodeCacheClient)

Usage:
    # Documentation search
    rag_client = RAGClient(base_url="http://nova-rag:8001")
    results = rag_client.query("how to extract PDF text")

    # Code cache
    cache_client = SemanticCodeCacheClient(base_url="http://nova-rag:8001")
    matches = cache_client.search_code(query="Extract PDF text", threshold=0.85)
"""

import logging
import os
from typing import List, Dict, Optional, Any
from datetime import datetime

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


class RAGClient:
    """
    Client for NOVA RAG microservice.

    Handles HTTP communication with the RAG service for documentation retrieval.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: int = 10,
        max_retries: int = 3
    ):
        """
        Initialize RAG client.

        Args:
            base_url: Base URL of RAG service (default: from RAG_SERVICE_URL env var)
            timeout: Request timeout in seconds (default: 10)
            max_retries: Max retry attempts for failed requests (default: 3)
        """
        self.base_url = base_url or os.getenv(
            'RAG_SERVICE_URL',
            'http://localhost:8001'  # Fallback for local dev
        )
        self.timeout = timeout

        # Configure session with retry logic
        self.session = requests.Session()
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=1,  # Wait 1s, 2s, 4s between retries
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        logger.info(f"RAG Client initialized with base_url: {self.base_url}")

    def query(
        self,
        query: str,
        top_k: int = 5,
        filters: Optional[Dict[str, str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Query the RAG service for relevant documentation.

        Args:
            query: Search query (e.g., "how to extract text from PDF")
            top_k: Number of results to return (default: 5)
            filters: Optional filters (source, topic)

        Returns:
            List of documentation chunks with text, source, topic, score

        Example:
            results = client.query("PDF extraction", top_k=3)
            for doc in results:
                print(f"[{doc['source']}] {doc['text']}")

        Raises:
            RAGServiceError: If RAG service is unavailable or returns error
        """
        try:
            response = self.session.post(
                f"{self.base_url}/rag/query",
                json={
                    "query": query,
                    "top_k": top_k,
                    "filters": filters or {}
                },
                timeout=self.timeout
            )
            response.raise_for_status()

            data = response.json()
            logger.info(f"RAG query successful: {data['count']} results for '{query}'")

            return data['results']

        except requests.exceptions.Timeout:
            logger.error(f"RAG query timeout after {self.timeout}s: {query}")
            raise RAGServiceError(f"RAG service timeout (query: {query})")

        except requests.exceptions.ConnectionError:
            logger.error(f"Failed to connect to RAG service at {self.base_url}")
            raise RAGServiceError(f"RAG service unavailable at {self.base_url}")

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 503:
                logger.warning("RAG service not ready yet (503)")
                raise RAGServiceError("RAG service initializing, please retry")
            else:
                logger.error(f"RAG query failed with HTTP {e.response.status_code}")
                raise RAGServiceError(f"RAG query failed: {e.response.text}")

        except Exception as e:
            logger.error(f"Unexpected error querying RAG service: {e}")
            raise RAGServiceError(f"RAG query error: {str(e)}")

    def get_stats(self) -> Dict[str, Any]:
        """
        Get RAG service statistics.

        Returns:
            Dict with total_documents, sources, topics, status

        Example:
            stats = client.get_stats()
            print(f"Vector store contains {stats['total_documents']} documents")
        """
        try:
            response = self.session.get(
                f"{self.base_url}/rag/stats",
                timeout=self.timeout
            )
            response.raise_for_status()

            data = response.json()
            logger.debug(f"RAG stats: {data}")

            return data

        except Exception as e:
            logger.error(f"Failed to get RAG stats: {e}")
            raise RAGServiceError(f"Failed to get RAG stats: {str(e)}")

    def health_check(self) -> bool:
        """
        Check if RAG service is healthy and ready.

        Returns:
            True if service is healthy and vector store is ready

        Example:
            if client.health_check():
                results = client.query("my query")
        """
        try:
            response = self.session.get(
                f"{self.base_url}/health",
                timeout=5  # Quick timeout for health checks
            )
            response.raise_for_status()

            data = response.json()
            is_ready = (
                data.get('status') == 'healthy' and
                data.get('vector_store_ready', False)
            )

            logger.debug(f"RAG health check: {data}")
            return is_ready

        except Exception as e:
            logger.warning(f"RAG health check failed: {e}")
            return False

    def reload_docs(self) -> Dict[str, Any]:
        """
        Trigger documentation reload (admin operation).

        Returns:
            Dict with reload status message

        Note:
            This is an admin operation that clears and reloads the vector store.
            Use sparingly as it temporarily disrupts RAG queries.
        """
        try:
            response = self.session.post(
                f"{self.base_url}/rag/reload",
                timeout=30  # Longer timeout for reload
            )
            response.raise_for_status()

            data = response.json()
            logger.info(f"RAG reload triggered: {data}")

            return data

        except Exception as e:
            logger.error(f"Failed to reload RAG docs: {e}")
            raise RAGServiceError(f"Failed to reload docs: {str(e)}")


class SemanticCodeCacheClient:
    """
    Client for Semantic Code Cache in NOVA RAG microservice.

    Handles HTTP communication for storing and retrieving cached code executions
    based on semantic similarity.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: int = 10,
        max_retries: int = 3
    ):
        """
        Initialize Semantic Code Cache client.

        Args:
            base_url: Base URL of RAG service (default: from RAG_SERVICE_URL env var)
            timeout: Request timeout in seconds (default: 10)
            max_retries: Max retry attempts for failed requests (default: 3)
        """
        self.base_url = base_url or os.getenv(
            'RAG_SERVICE_URL',
            'http://localhost:8001'
        )
        self.timeout = timeout

        # Configure session with retry logic
        self.session = requests.Session()
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        logger.info(f"Semantic Code Cache Client initialized with base_url: {self.base_url}")

    def search_code(
        self,
        query: str,
        threshold: float = 0.85,
        top_k: int = 5,
        available_keys: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for similar cached code.

        Args:
            query: Search query (task description + input schema + insights)
            threshold: Minimum similarity score (0-1, default: 0.85)
            top_k: Maximum number of results (default: 5)
            available_keys: List of keys available in current context (for filtering)

        Returns:
            List of code matches with score, code, metadata

        Example:
            matches = client.search_code(
                query="Extract text from PDF\\nInput: pdf_data (base64)",
                threshold=0.85,
                available_keys=["pdf_data", "client_id"]
            )
            if matches:
                best_code = matches[0]['code']

        Raises:
            RAGServiceError: If service is unavailable or returns error
        """
        try:
            payload = {
                "query": query,
                "threshold": threshold,
                "top_k": top_k
            }
            if available_keys is not None:
                payload["available_keys"] = available_keys

            response = self.session.post(
                f"{self.base_url}/code/search",
                json=payload,
                timeout=self.timeout
            )
            response.raise_for_status()

            data = response.json()
            logger.info(f"Code cache search: {data['count']} matches above threshold {threshold}")

            return data['matches']

        except requests.exceptions.Timeout:
            logger.error(f"Code cache search timeout after {self.timeout}s")
            return []  # Return empty list on timeout (fail gracefully)

        except requests.exceptions.ConnectionError:
            logger.error(f"Failed to connect to code cache at {self.base_url}")
            return []  # Return empty list on connection error

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 503:
                logger.warning("Code cache service not ready yet (503)")
                return []
            else:
                logger.error(f"Code cache search failed with HTTP {e.response.status_code}")
                return []

        except Exception as e:
            logger.error(f"Unexpected error searching code cache: {e}")
            return []

    def save_code(
        self,
        ai_description: str,
        input_schema: Dict,
        insights: List[str],
        config: Dict,
        code: str,
        node_action: str,
        node_description: str,
        libraries_used: List[str]
    ) -> bool:
        """
        Save successful code execution to semantic cache.

        Args:
            ai_description: Natural language description of what code does
            input_schema: Compact input data schema
            insights: Context insights
            config: Configuration flags (credentials, etc.)
            code: The Python code
            node_action: Action type from workflow node
            node_description: Description from workflow node
            libraries_used: List of libraries imported in code

        Returns:
            True if saved successfully, False otherwise

        Example:
            success = client.save_code(
                ai_description="Extracts text from PDF using PyMuPDF",
                input_schema={"pdf_data": "base64_large"},
                insights=["PDF format", "Text extraction"],
                config={"has_credentials": False},
                code="import fitz\\n...",
                node_action="extract_pdf",
                node_description="Extract invoice text",
                libraries_used=["fitz", "base64"]
            )
        """
        try:
            response = self.session.post(
                f"{self.base_url}/code/save",
                json={
                    "ai_description": ai_description,
                    "input_schema": input_schema,
                    "insights": insights,
                    "config": config,
                    "code": code,
                    "node_action": node_action,
                    "node_description": node_description,
                    "metadata": {
                        "success_count": 1,
                        "created_at": datetime.now().isoformat(),
                        "libraries_used": libraries_used
                    }
                },
                timeout=self.timeout
            )
            response.raise_for_status()

            data = response.json()
            if data.get("success"):
                logger.info(f"✓ Code saved to cache: {data.get('id')}")
                return True
            else:
                logger.warning(f"Code save returned success=False: {data}")
                return False

        except Exception as e:
            logger.error(f"Failed to save code to cache: {e}")
            return False  # Fail gracefully


class RAGServiceError(Exception):
    """Exception raised when RAG service is unavailable or returns error."""
    pass


# Singleton instances for app-wide use
_rag_client: Optional[RAGClient] = None
_code_cache_client: Optional[SemanticCodeCacheClient] = None


def get_rag_client() -> RAGClient:
    """
    Get singleton RAG client instance.

    Returns:
        Global RAGClient instance

    Example:
        from core.rag_client import get_rag_client

        client = get_rag_client()
        results = client.query("my query")
    """
    global _rag_client

    if _rag_client is None:
        _rag_client = RAGClient()

    return _rag_client


def get_code_cache_client() -> SemanticCodeCacheClient:
    """
    Get singleton Semantic Code Cache client instance.

    Returns:
        Global SemanticCodeCacheClient instance

    Example:
        from core.rag_client import get_code_cache_client

        client = get_code_cache_client()
        matches = client.search_code("Extract PDF text", threshold=0.85)
    """
    global _code_cache_client

    if _code_cache_client is None:
        _code_cache_client = SemanticCodeCacheClient()

    return _code_cache_client
