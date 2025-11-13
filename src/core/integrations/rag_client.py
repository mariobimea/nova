"""
RAG Client for NOVA Workflow Engine

Client to interact with nova-rag microservice for documentation search.
Used by CodeGeneratorAgent for tool calling.
"""

import os
import logging
from typing import List, Dict, Optional
import httpx

logger = logging.getLogger(__name__)


class RAGClient:
    """
    Client for nova-rag microservice.

    Provides documentation search capabilities for AI agents.

    Environment Variables:
        RAG_SERVICE_URL: URL of nova-rag service (e.g., "https://nova-rag.railway.app")

    Example:
        client = RAGClient()
        results = await client.search(
            query="how to extract text from PDF",
            library="pymupdf",
            top_k=3
        )
    """

    def __init__(self, base_url: Optional[str] = None, timeout: int = 10):
        """
        Initialize RAG client.

        Args:
            base_url: Base URL of RAG service (default: from RAG_SERVICE_URL env var)
            timeout: Request timeout in seconds (default: 10)
        """
        self.base_url = base_url or os.getenv("RAG_SERVICE_URL")

        if not self.base_url:
            raise ValueError(
                "RAG_SERVICE_URL environment variable not set. "
                "Set it to the nova-rag service URL (e.g., 'https://nova-rag.railway.app')"
            )

        # Remove trailing slash
        self.base_url = self.base_url.rstrip('/')

        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=timeout)

        logger.info(f"RAGClient initialized with base_url: {self.base_url}")

    async def health_check(self) -> Dict:
        """
        Check if RAG service is healthy and ready.

        Returns:
            Health status dict with:
            - status: "healthy" or "initializing"
            - vector_store_ready: bool
            - documents_loaded: int

        Raises:
            httpx.HTTPError: If service is unreachable
        """
        try:
            response = await self.client.get(f"{self.base_url}/health")
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(f"RAG health check failed: {e}")
            raise

    async def search(
        self,
        query: str,
        library: Optional[str] = None,
        topic: Optional[str] = None,
        top_k: int = 5
    ) -> List[Dict]:
        """
        Search RAG vector store for relevant documentation.

        Args:
            query: Search query (e.g., "how to extract text from PDF")
            library: Optional library filter (e.g., "pymupdf", "easyocr")
            topic: Optional topic filter (e.g., "quickstart", "official")
            top_k: Number of results to return (1-20)

        Returns:
            List of results, each with:
            - text: str (documentation chunk)
            - source: str (library name)
            - topic: str (document type)
            - score: float (similarity score 0-1, higher is better)

        Example:
            results = await client.search(
                query="extract text from PDF",
                library="pymupdf",
                top_k=3
            )

            for result in results:
                print(f"Score: {result['score']:.2f}")
                print(f"Source: {result['source']}")
                print(f"Text: {result['text'][:100]}...")

        Raises:
            httpx.HTTPError: If service returns error
            ValueError: If RAG service is not ready
        """
        # Build filters
        filters = {}
        if library:
            filters['source'] = library
        if topic:
            filters['topic'] = topic

        # Build request
        request_data = {
            "query": query,
            "top_k": min(max(top_k, 1), 20),  # Clamp to 1-20
        }

        if filters:
            request_data['filters'] = filters

        try:
            response = await self.client.post(
                f"{self.base_url}/rag/query",
                json=request_data
            )
            response.raise_for_status()

            data = response.json()

            logger.info(
                f"RAG search successful: query='{query[:50]}...', "
                f"results={data['count']}, filters={filters}"
            )

            return data['results']

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 503:
                raise ValueError(
                    "RAG service not ready yet. Vector store is still initializing."
                )
            logger.error(f"RAG search failed: {e}")
            raise

        except httpx.HTTPError as e:
            logger.error(f"RAG search failed: {e}")
            raise

    async def get_stats(self) -> Dict:
        """
        Get RAG vector store statistics.

        Returns:
            Stats dict with:
            - total_documents: int
            - sources: List[str] (available libraries)
            - topics: List[str] (available topics)
            - status: str ("ready" or "loading")
        """
        try:
            response = await self.client.get(f"{self.base_url}/rag/stats")
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(f"RAG stats request failed: {e}")
            raise

    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()

    async def __aenter__(self):
        """Context manager support."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager support."""
        await self.close()
