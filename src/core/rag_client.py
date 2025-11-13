"""
RAG Client for NOVA

HTTP client to communicate with the nova-rag microservice.
Provides vector search over documentation for AI code generation.

Usage:
    client = RAGClient(base_url="http://nova-rag:8001")
    results = client.query("how to extract PDF text")
"""

import logging
import os
from typing import List, Dict, Optional, Any

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


class RAGServiceError(Exception):
    """Exception raised when RAG service is unavailable or returns error."""
    pass


# Singleton instance for app-wide use
_rag_client: Optional[RAGClient] = None


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
