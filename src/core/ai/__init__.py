"""
AI module for NOVA - Code generation components.

This module provides AI-powered code generation capabilities:
- KnowledgeManager: Manages documentation retrieval from RAG service
- Tools: Function calling definitions for OpenAI API

NOTE: This module ONLY uses the remote RAG service (nova-rag).
Local vector store has been removed for simplicity.
"""

from .knowledge_manager import KnowledgeManager
from .tools import get_all_tools, execute_search_documentation

__all__ = [
    "KnowledgeManager",
    "get_all_tools",
    "execute_search_documentation",
]
