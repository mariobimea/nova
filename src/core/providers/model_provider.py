"""
Model Provider Abstract Interface

Defines the contract for all LLM providers (OpenAI, Anthropic, etc.).
This abstraction allows NOVA to switch between different AI providers seamlessly.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class ModelProvider(ABC):
    """
    Abstract interface for LLM providers.

    All providers must implement:
    1. generate_code_with_tools() - Generate Python code using AI
    2. get_pricing() - Return pricing information for cost tracking
    3. get_model_name() - Return the model identifier

    This allows NOVA to:
    - Support multiple AI providers (OpenAI, Anthropic, etc.)
    - Switch models dynamically per workflow/node
    - Track costs accurately across different models
    - Test with different providers easily
    """

    @abstractmethod
    async def generate_code_with_tools(
        self,
        task: str,
        context: Dict[str, Any],
        error_history: Optional[List[Dict]] = None,
        system_message: Optional[str] = None,
        knowledge_manager: Optional[Any] = None
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Generate Python code using AI with optional tool calling.

        This is the main method for code generation. The AI can use tools
        (like search_documentation) to find relevant API docs before generating code.

        Args:
            task: Natural language description of what the code should do
            context: Current workflow context (data available to the code)
            error_history: Optional list of previous failed attempts with errors
            system_message: Optional custom system prompt (for AI self-determination)
            knowledge_manager: Optional KnowledgeManager for documentation search

        Returns:
            Tuple of (generated_code, tool_metadata) where:
            - generated_code: Python code as string
            - tool_metadata: Dict with tool calling info (for debugging/tracking):
                {
                    "tool_calls": [...],  # List of tool calls made
                    "tool_iterations": 3,  # Number of iterations
                    "total_tool_calls": 5,  # Total tools called
                    "context_summary": "..."  # What context the AI saw
                }

        Raises:
            ExecutorError: If code generation fails
        """
        pass

    @abstractmethod
    def get_pricing(self) -> Dict[str, float]:
        """
        Get pricing information for this model.

        Used for cost tracking and analytics. Prices are per 1M tokens.

        Returns:
            Dictionary with pricing:
            {
                "input": 0.25,  # $ per 1M input tokens
                "output": 2.00,  # $ per 1M output tokens
                "cached_input": 0.03  # $ per 1M cached input tokens (if supported)
            }

        Example:
            >>> provider = OpenAIProvider("gpt-4o-mini")
            >>> provider.get_pricing()
            {"input": 0.15, "output": 0.60}
        """
        pass

    @abstractmethod
    def get_model_name(self) -> str:
        """
        Get the model identifier.

        Returns the canonical model name (e.g., "gpt-4o-mini", "claude-sonnet-4-5").
        Used for tracking which model generated each piece of code.

        Returns:
            Model name as string

        Example:
            >>> provider = OpenAIProvider("gpt-4o-mini")
            >>> provider.get_model_name()
            "gpt-4o-mini"
        """
        pass

    def estimate_tokens(self, text: str) -> int:
        """
        Estimate token count for text.

        Default implementation: ~4 characters per token (rough approximation).
        Providers can override with more accurate tokenization.

        Args:
            text: Text to estimate tokens for

        Returns:
            Estimated token count

        Example:
            >>> provider.estimate_tokens("Hello world")
            2
        """
        return len(text) // 4

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """
        Estimate cost for token usage.

        Uses get_pricing() to calculate total cost.

        Args:
            input_tokens: Number of input tokens used
            output_tokens: Number of output tokens generated

        Returns:
            Estimated cost in USD

        Example:
            >>> provider = OpenAIProvider("gpt-4o-mini")
            >>> provider.estimate_cost(1000, 500)
            0.00045  # $0.15/1M * 1000 + $0.60/1M * 500
        """
        pricing = self.get_pricing()
        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]
        return round(input_cost + output_cost, 6)
