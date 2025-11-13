"""
AI Tools - Function calling definitions for OpenAI API.

This module defines tools that the AI can use during code generation:
- search_documentation: Search RAG service (nova-rag) for integration docs
"""

import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)


def get_search_documentation_tool() -> Dict[str, Any]:
    """
    Returns OpenAI function calling definition for search_documentation tool.

    This tool allows the AI to search the RAG service (nova-rag) for relevant documentation
    during code generation. The AI can:
    - Search for specific API patterns
    - Filter by integration/library
    - Request multiple results
    - Make multiple searches iteratively

    Returns:
        Tool definition dict compatible with OpenAI chat.completions API

    Example usage by AI:
        {
            "tool_calls": [{
                "function": {
                    "name": "search_documentation",
                    "arguments": {
                        "query": "open PDF from base64 bytes",
                        "source": "pymupdf",
                        "top_k": 3
                    }
                }
            }]
        }
    """
    return {
        "type": "function",
        "function": {
            "name": "search_documentation",
            "description": (
                "Search NOVA's integration documentation for code examples, API references, "
                "and usage patterns. Use this to find information about:\n"
                "- PyMuPDF (pymupdf): PDF text extraction, form parsing\n"
                "- EasyOCR (easyocr): Optical character recognition for scanned documents\n"
                "- IMAP (imap): Reading emails from inbox\n"
                "- SMTP (smtp): Sending emails\n"
                "- PostgreSQL (postgres): Database operations\n"
                "- Regex (regex): Pattern matching and text extraction\n\n"
                "Returns relevant code snippets and documentation chunks."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "Search query describing what you need to know. "
                            "Examples: 'open PDF from base64 bytes', 'extract text with OCR', "
                            "'send email with attachment', 'regex pattern for invoice numbers'"
                        )
                    },
                    "source": {
                        "type": "string",
                        "enum": ["pymupdf", "easyocr", "imap", "smtp", "postgres", "regex"],
                        "description": (
                            "Optional: Filter results to specific integration/library. "
                            "Use this when you know which library you need. "
                            "If unsure, omit this parameter to search all docs."
                        )
                    },
                    "top_k": {
                        "type": "integer",
                        "default": 3,
                        "minimum": 1,
                        "maximum": 10,
                        "description": (
                            "Number of documentation chunks to return (default: 3). "
                            "Use higher values (5-10) for complex tasks requiring more context."
                        )
                    }
                },
                "required": ["query"]
            }
        }
    }


def format_search_results(
    results: List[Dict[str, Any]],
    query: str,
    include_metadata: bool = False
) -> str:
    """
    Format RAG service search results for AI consumption.

    Args:
        results: List of dicts from RAGClient.query() with keys:
                 - text: Document chunk text
                 - source: Source library (e.g., "pymupdf")
                 - topic: Topic/category
                 - score: Relevance score (higher = better match)
        query: Original search query (for context)
        include_metadata: Include scores and source info

    Returns:
        Formatted string ready to send back to AI

    Example output:
        SEARCH RESULTS for "open PDF from bytes" (3 results):

        [1] Source: pymupdf | Relevance: 0.92
        Opening Documents

        Access supported file types with:

        ```python
        doc = pymupdf.open(filename)
        # or from bytes:
        doc = pymupdf.open(stream=BytesIO(data), filetype='pdf')
        ```

        ---

        [2] Source: pymupdf | Relevance: 0.89
        ...
    """
    if not results:
        return f"No documentation found for query: '{query}'"

    lines = []
    lines.append(f"SEARCH RESULTS for \"{query}\" ({len(results)} result{'s' if len(results) != 1 else ''}):")
    lines.append("")

    for i, result in enumerate(results, 1):
        # Header with metadata
        if include_metadata:
            header = f"[{i}] Source: {result.get('source', 'unknown')}"
            if 'score' in result:
                header += f" | Relevance: {result['score']:.2f}"
            lines.append(header)
        else:
            lines.append(f"[{i}]")

        # Document text
        text = result.get('text', '').strip()
        lines.append(text)

        # Separator
        if i < len(results):
            lines.append("")
            lines.append("---")
            lines.append("")

    return "\n".join(lines)


def execute_search_documentation(
    rag_client,
    query: str,
    source: Optional[str] = None,
    top_k: int = 3
) -> str:
    """
    Execute a documentation search via RAG service and return formatted results.

    This is the actual implementation that gets called when the AI
    uses the search_documentation tool.

    Args:
        rag_client: RAGClient instance (from get_rag_client())
        query: Search query from AI
        source: Optional source filter (e.g., "pymupdf")
        top_k: Number of results to return

    Returns:
        Formatted search results as string

    Raises:
        Exception: If RAG service is unavailable or search fails
    """
    logger.info(f"AI searching docs via RAG: query='{query}', source={source}, top_k={top_k}")

    try:
        # Build filters
        filters = {}
        if source:
            filters["source"] = source

        # Execute search via RAG service
        results = rag_client.query(
            query=query,
            top_k=top_k,
            filters=filters if filters else None
        )

        # Format results
        formatted = format_search_results(
            results=results,
            query=query,
            include_metadata=True
        )

        logger.info(f"RAG search returned {len(results)} results")
        logger.debug(f"Formatted results:\n{formatted[:200]}...")

        return formatted

    except Exception as e:
        error_msg = f"Error searching documentation via RAG service: {e}"
        logger.error(error_msg)
        return f"ERROR: {error_msg}\n\nTry a different query or generate code without documentation."


# Registry of all available tools
AVAILABLE_TOOLS = {
    "search_documentation": get_search_documentation_tool()
}


def get_all_tools() -> List[Dict[str, Any]]:
    """
    Get list of all available tools for OpenAI API.

    Returns:
        List of tool definitions

    Example:
        >>> tools = get_all_tools()
        >>> response = openai.chat.completions.create(
        ...     model="gpt-4o-mini",
        ...     messages=[...],
        ...     tools=tools
        ... )
    """
    return list(AVAILABLE_TOOLS.values())
