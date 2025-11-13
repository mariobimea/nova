"""
Integration clients for external services.

This module provides clients for:
- RAG Service: Documentation search via nova-rag microservice
"""

from .rag_client import RAGClient

__all__ = ["RAGClient"]
