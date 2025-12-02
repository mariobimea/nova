"""
Anthropic Model Provider

Implements ModelProvider interface for Anthropic Claude models.
Supports: claude-sonnet-4-5, claude-haiku-4-5, claude-opus-4-5
"""

import json
import time
import logging
from typing import Dict, Any, List, Optional, Tuple

from .model_provider import ModelProvider
from ..exceptions import ExecutorError

logger = logging.getLogger(__name__)


class AnthropicProvider(ModelProvider):
    """
    Anthropic provider implementation.

    Supports dynamic code generation with tool calling (documentation search).
    Based on Claude's native tool use capabilities.
    """

    # Model configurations (pricing per 1M tokens as of Dec 2025)
    MODELS = {
        "claude-sonnet-4-5": {
            "api_name": "claude-sonnet-4-5-20250929",
            "input_price": 3.00,  # $ per 1M tokens
            "output_price": 15.00,
            "max_tokens": 8192,
            "context_window": 200000  # 200K, expandable to 1M
        },
        "claude-haiku-4-5": {
            "api_name": "claude-haiku-4-5-20250929",
            "input_price": 0.80,
            "output_price": 4.00,
            "max_tokens": 8192,
            "context_window": 200000
        },
        "claude-opus-4-5": {
            "api_name": "claude-opus-4-5-20250929",
            "input_price": 15.00,
            "output_price": 75.00,
            "max_tokens": 8192,
            "context_window": 200000
        },
        # Aliases for convenience
        "sonnet": {
            "api_name": "claude-sonnet-4-5-20250929",
            "input_price": 3.00,
            "output_price": 15.00,
            "max_tokens": 8192,
            "context_window": 200000
        },
        "haiku": {
            "api_name": "claude-haiku-4-5-20250929",
            "input_price": 0.80,
            "output_price": 4.00,
            "max_tokens": 8192,
            "context_window": 200000
        },
        "opus": {
            "api_name": "claude-opus-4-5-20250929",
            "input_price": 15.00,
            "output_price": 75.00,
            "max_tokens": 8192,
            "context_window": 200000
        }
    }

    def __init__(self, model_name: str, api_key: Optional[str] = None):
        """
        Initialize Anthropic provider.

        Args:
            model_name: Model to use (e.g., "claude-sonnet-4-5", "sonnet")
            api_key: Optional Anthropic API key (or use ANTHROPIC_API_KEY env var)

        Raises:
            ValueError: If model is not supported
            ImportError: If anthropic library not installed
        """
        if model_name not in self.MODELS:
            raise ValueError(
                f"Unsupported Anthropic model: '{model_name}'. "
                f"Supported models: {list(self.MODELS.keys())}"
            )

        self.model_name = model_name
        self.model_config = self.MODELS[model_name]

        # Initialize Anthropic client
        import os
        api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY environment variable is required. "
                "Get API key at: https://console.anthropic.com/settings/keys"
            )

        try:
            import anthropic
            self.client = anthropic.Anthropic(api_key=api_key)
        except ImportError:
            raise ImportError(
                "Anthropic library not installed. Install with: pip install anthropic"
            )

        logger.info(f"AnthropicProvider initialized with model: {model_name}")

    async def generate_code_with_tools(
        self,
        task: str,
        context: Dict[str, Any],
        error_history: Optional[List[Dict]] = None,
        system_message: Optional[str] = None,
        knowledge_manager: Optional[Any] = None
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Generate Python code using Anthropic API with tool calling.

        Args:
            task: Natural language task description
            context: Workflow context dictionary
            error_history: Optional list of previous failed attempts
            system_message: Optional custom system prompt
            knowledge_manager: Optional KnowledgeManager for doc search

        Returns:
            Tuple of (generated_code, tool_metadata)

        Raises:
            ExecutorError: If generation fails
        """
        from ..ai.tools import execute_search_documentation

        try:
            logger.info(f"Generating code with {self.model_name} (tool calling enabled)...")
            start_time = time.time()

            # Track all tool calls
            all_tool_calls = []

            # Build system message
            if system_message:
                system_content = system_message
            else:
                system_content = self._build_default_system_prompt()

            # Build initial messages
            messages = [
                {
                    "role": "user",
                    "content": self._build_user_prompt(task, context, error_history, knowledge_manager)
                }
            ]

            # Define tools for Claude
            tools = self._get_claude_tools()

            # Tool calling loop
            max_tool_iterations = 15
            tool_call_count = 0

            for iteration in range(max_tool_iterations):
                logger.info(f"🔄 Tool calling iteration {iteration + 1}/{max_tool_iterations}")

                # Call Anthropic API
                response = self.client.messages.create(
                    model=self.model_config["api_name"],
                    max_tokens=self.model_config["max_tokens"],
                    system=system_content,
                    messages=messages,
                    tools=tools
                )

                # Process response
                stop_reason = response.stop_reason

                logger.debug(
                    f"Anthropic response - stop_reason: {stop_reason}, "
                    f"content_blocks: {len(response.content)}"
                )

                # Check for tool use
                tool_use_blocks = [
                    block for block in response.content
                    if block.type == "tool_use"
                ]
                text_blocks = [
                    block for block in response.content
                    if block.type == "text"
                ]

                # Log any text thinking
                for text_block in text_blocks:
                    if text_block.text:
                        logger.info(f"💭 AI thinking: {text_block.text[:150]}...")

                # AI wants to use tools
                if tool_use_blocks:
                    tool_call_count += len(tool_use_blocks)
                    logger.info(f"🔧 AI requested {len(tool_use_blocks)} tool call(s)")

                    # Add assistant response to messages
                    messages.append({
                        "role": "assistant",
                        "content": response.content
                    })

                    # Execute each tool and collect results
                    tool_results = []

                    for tool_use in tool_use_blocks:
                        function_name = tool_use.name
                        arguments = tool_use.input
                        tool_use_id = tool_use.id

                        logger.info(f"Executing tool: {function_name}({arguments})")

                        if function_name == "search_documentation":
                            # Execute search
                            result = execute_search_documentation(
                                rag_client=knowledge_manager.rag_client if knowledge_manager else None,
                                query=arguments.get("query"),
                                top_k=arguments.get("top_k", 5)
                            )

                            # Track tool call
                            all_tool_calls.append({
                                "iteration": iteration + 1,
                                "function": function_name,
                                "arguments": arguments,
                                "result_preview": result[:500] if result else None
                            })

                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": tool_use_id,
                                "content": result
                            })
                        else:
                            # Unknown tool
                            error_msg = f"ERROR: Unknown tool '{function_name}'"
                            all_tool_calls.append({
                                "iteration": iteration + 1,
                                "function": function_name,
                                "arguments": arguments,
                                "error": error_msg
                            })
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": tool_use_id,
                                "content": error_msg,
                                "is_error": True
                            })

                    # Add tool results to messages
                    messages.append({
                        "role": "user",
                        "content": tool_results
                    })

                    continue

                # AI generated code (no tool calls, or stop_reason is "end_turn")
                else:
                    # Extract text content
                    raw_code = ""
                    for block in response.content:
                        if block.type == "text":
                            raw_code += block.text

                    if not raw_code:
                        raise ExecutorError(
                            f"Anthropic returned empty response. "
                            f"Stop reason: {stop_reason}, "
                            f"Model: {self.model_name}, "
                            f"Iteration: {iteration + 1}/{max_tool_iterations}"
                        )

                    generation_time_ms = int((time.time() - start_time) * 1000)
                    logger.info(
                        f"✅ Code generated after {tool_call_count} tool call(s) "
                        f"in {generation_time_ms}ms"
                    )

                    # Clean and validate
                    code = self._clean_code_blocks(raw_code)

                    if not code:
                        raise ExecutorError("Generated code is empty after cleaning")

                    self._validate_syntax(code)

                    logger.debug(f"Generated code ({len(code)} chars):\n{code}")

                    # Return metadata
                    context_summary = ""
                    if knowledge_manager:
                        context_summary = knowledge_manager.summarize_context(context)

                    tool_metadata = {
                        "tool_calls": all_tool_calls,
                        "tool_iterations": iteration + 1,
                        "total_tool_calls": len(all_tool_calls),
                        "context_summary": context_summary
                    }

                    return code, tool_metadata

            # Exceeded max iterations
            raise ExecutorError(
                f"Exceeded max tool iterations ({max_tool_iterations}) without generating code"
            )

        except Exception as e:
            if isinstance(e, ExecutorError):
                raise

            logger.exception(f"Anthropic code generation failed: {e}")
            raise ExecutorError(f"Failed to generate code: {e}")

    def _get_claude_tools(self) -> List[Dict]:
        """Get tool definitions in Claude's format."""
        return [
            {
                "name": "search_documentation",
                "description": (
                    "Search the NOVA documentation and integration guides for code examples, "
                    "API references, and usage patterns. Use this to find how to use specific "
                    "libraries (PyMuPDF, EasyOCR, pandas, etc.) or integrations (email, HTTP, etc.)"
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query describing what you're looking for (e.g., 'extract text from PDF PyMuPDF', 'send email SMTP')"
                        },
                        "top_k": {
                            "type": "integer",
                            "description": "Number of results to return (default: 5)",
                            "default": 5
                        }
                    },
                    "required": ["query"]
                }
            }
        ]

    def _build_default_system_prompt(self) -> str:
        """Build default system prompt for code generation."""
        return (
            "You are a Python code generator for the NOVA workflow engine.\n\n"
            "Your job: Generate Python code that solves tasks by processing data in a sandboxed environment.\n\n"

            "TOOLS AVAILABLE:\n"
            "- search_documentation(query, top_k?): Search integration docs for code examples\n\n"

            "WORKFLOW:\n"
            "1. Analyze the task and available context\n"
            "2. IF you need library docs: Use search_documentation() to find relevant API examples\n"
            "   - Search for specific patterns (e.g., 'extract text PDF PyMuPDF', 'send email SMTP')\n"
            "   - You can search 2-3 times MAX if needed\n"
            "   - If the task is simple and you know the syntax, DON'T search\n"
            "3. Generate Python code that solves the task\n\n"

            "IMPORTANT - DON'T OVER-USE TOOLS:\n"
            "- Only search docs if you're unsure about syntax or API usage\n"
            "- For simple tasks (read file, parse JSON, etc.) → generate code directly\n"
            "- 1-3 searches should be enough for any task\n\n"

            "CODE REQUIREMENTS:\n"
            "1. Use ONLY pre-installed libraries (see ENVIRONMENT below)\n"
            "2. Access context with: value = context['key'] or context.get('key', default)\n"
            "3. Update context with: context['new_key'] = result\n"
            "4. Include proper error handling (try/except)\n"
            "5. Code MUST end with: print(json.dumps(context, ensure_ascii=False, indent=2))\n"
            "6. Return ONLY code, no explanations or markdown\n\n"

            "⚠️ CRITICAL - ACCESSING CONTEXT:\n"
            "The context dict is injected at the start of your code automatically.\n\n"
            "✅ CORRECT:\n"
            "   user = context['email_user']           # Extract from context first\n"
            "   password = context['email_password']\n"
            "   host = context.get('smtp_host', 'smtp.gmail.com')  # With default\n"
            "   # ... use the variables ...\n\n"
            "❌ WRONG (will cause NameError):\n"
            "   send_email(email_user, password)       # Variables don't exist!\n"
            "   def process(email_user, password):     # Must extract from context first\n\n"

            "⚠️ CRITICAL - OUTPUT REQUIREMENT:\n"
            "Your code MUST print the updated context at the end:\n"
            "   print(json.dumps(context, ensure_ascii=False, indent=2))\n\n"
            "Without this print, the executor cannot read your results and will FAIL.\n\n"

            "ENVIRONMENT (E2B Sandbox):\n"
            "- Python 3.11 in isolated container\n"
            "- Pre-installed packages:\n"
            "  * PyMuPDF (import as 'fitz') - PDF processing\n"
            "  * EasyOCR - OCR for images\n"
            "  * requests - HTTP/API calls\n"
            "  * pandas - Data analysis\n"
            "  * psycopg2 - PostgreSQL\n"
            "  * Pillow (PIL) - Image processing\n"
            "- Standard library available: json, re, base64, csv, email, smtplib, imaplib, etc.\n"
            "- Network access enabled\n"
        )

    def _build_user_prompt(
        self,
        task: str,
        context: Dict[str, Any],
        error_history: Optional[List[Dict]],
        knowledge_manager: Optional[Any]
    ) -> str:
        """Build user prompt for code generation."""
        context_summary = ""
        if knowledge_manager:
            context_summary = knowledge_manager.summarize_context(context)
        else:
            # Fallback: basic context summary
            context_summary = f"Available keys: {list(context.keys())}"

        prompt = f"TASK:\n{task}\n\nCONTEXT AVAILABLE:\n{context_summary}\n\n"

        if error_history:
            prompt += f"PREVIOUS FAILED ATTEMPTS:\n{self._format_error_history(error_history)}\n\n"

        prompt += "Use search_documentation() to find relevant docs if needed, then generate code."

        return prompt

    def _format_error_history(self, error_history: List[Dict]) -> str:
        """Format error history for prompt."""
        if not error_history:
            return ""

        lines = []
        for i, attempt in enumerate(error_history, 1):
            error = attempt.get("error", "Unknown error")
            code = attempt.get("code", "")

            lines.append(f"Attempt {i}: FAILED")
            lines.append(f"Error: {error[:300]}")
            if code:
                lines.append(f"Code preview: {code[:200]}...")
            lines.append("")

        return "\n".join(lines)

    def _clean_code_blocks(self, code: str) -> str:
        """Remove markdown code blocks from AI output."""
        import re

        # Remove markdown code blocks
        code_block_pattern = r'```(?:python)?\s*\n(.*?)\n```'
        matches = re.findall(code_block_pattern, code, re.DOTALL)

        if matches:
            code = matches[0]

        # Remove explanation lines
        lines = code.split('\n')
        cleaned_lines = []

        for line in lines:
            stripped = line.strip().lower()

            if any(phrase in stripped for phrase in [
                "here's the code",
                "here is the code",
                "this code will",
                "the code above",
                "explanation:",
                "note:",
            ]):
                continue

            cleaned_lines.append(line)

        return '\n'.join(cleaned_lines).strip()

    def _validate_syntax(self, code: str) -> None:
        """Validate Python syntax."""
        import ast
        from ..exceptions import CodeExecutionError

        try:
            ast.parse(code)
        except SyntaxError as e:
            raise CodeExecutionError(
                message=f"Generated code has invalid syntax: {e}",
                code=code,
                error_details=str(e)
            )

    def get_pricing(self) -> Dict[str, float]:
        """Get pricing for this model."""
        return {
            "input": self.model_config["input_price"],
            "output": self.model_config["output_price"]
        }

    async def generate_text(
        self,
        prompt: str,
        temperature: float = 0.1,
        max_tokens: int = 200
    ) -> str:
        """
        Generate text with Anthropic (simple mode, no tool calling).

        Used for AI validation, summaries, etc.

        Args:
            prompt: Text prompt
            temperature: Temperature (0.0-1.0, lower = more deterministic)
            max_tokens: Max tokens to generate

        Returns:
            Generated text
        """
        import asyncio

        try:
            # Run synchronous Anthropic call in executor
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.messages.create(
                    model=self.model_config["api_name"],
                    max_tokens=max_tokens,
                    temperature=temperature,
                    messages=[{"role": "user", "content": prompt}]
                )
            )

            # Extract text from response
            text_content = ""
            for block in response.content:
                if block.type == "text":
                    text_content += block.text

            return text_content

        except Exception as e:
            logger.error(f"Anthropic generate_text failed: {e}")
            raise ExecutorError(f"Anthropic API error: {e}")

    def get_model_name(self) -> str:
        """Get model name."""
        return self.model_name
